from tkinter.filedialog import askdirectory
from tkinter import *
import os
import copy

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.cm

from cichlidanalysis.utils.timings import load_timings
from cichlidanalysis.analysis.processing import feature_daily
from cichlidanalysis.plotting.speed_plots import plot_ridge_plots
from cichlidanalysis.analysis.run_binned_als import setup_run_binned
from cichlidanalysis.analysis.run_feature_vector import setup_feature_vector_data
from cichlidanalysis.io.io_feature_vector import load_diel_pattern
from cichlidanalysis.analysis.linear_regression import run_linear_reg, plt_lin_reg
from cichlidanalysis.plotting.plot_pca import plot_loadings, plot_2D_pc_space, plot_2D_pc_space_orig, \
    plot_variance_explained, plot_factor_loading_matrix, pc_loadings_on_2D, plot_reconstruct_pc, plot_3D_pc_space
# insipired by https://towardsdatascience.com/pca-using-python-scikit-learn-e653f8989e60


def reorganise_behav(fish_tracks_bin, feature, feature_id, row_id='FishID', col_id='time_of_day_dt'):
    """ This takes in fish_tracks_bin data and reorganises so that each row is a fish, each column is a time bin and the
     values are the daily average of a feature. This is used for PCA analysis

    :param fish_tracks_bin:
    :param feature:
    :param feature_id:
    :param row_id:
    :param col_id:
    :return:
    """
    subset = fish_tracks_bin.loc[:, [row_id, col_id, feature, 'day_n']]
    subset_2 = subset.groupby([row_id, col_id]).mean()
    subset_3 = subset_2.reset_index().drop(columns='day_n')
    feature_reorg = subset_3.pivot(index=row_id, columns=col_id).add_prefix(feature_id).droplevel(0, axis=1)
    return feature_reorg


def fish_bin_pca_df(fish_tracks_bin, ronco_data):
    # reshape fish_tracks_bin by making FishID the rows
    org_spd = reorganise_behav(fish_tracks_bin, feature='speed_mm', feature_id='spd_', row_id='FishID',
                               col_id='time_of_day_dt')
    org_rest = reorganise_behav(fish_tracks_bin, feature='rest', feature_id='rest_', row_id='FishID',
                                col_id='time_of_day_dt')
    org_vp = reorganise_behav(fish_tracks_bin, feature='vertical_pos', feature_id='vp_', row_id='FishID',
                              col_id='time_of_day_dt')

    pca_df = pd.concat([org_spd, org_rest, org_vp], axis=1)  # .reset_index()
    to_add = fish_tracks_bin.loc[:, ['FishID', 'sex', 'size_male', 'size_female', 'habitat', 'diet', 'species']
             ].drop_duplicates().reset_index(drop=True)
    combined = to_add.merge(ronco_data.rename(columns={"sp": "species"}), 'left', on='species')
    to_add_ronco = combined.groupby(['FishID'], as_index=False).agg(
        {'species': 'first', 'sex': 'first', 'size_male': 'mean'
            , 'size_female': 'mean', 'habitat': 'first',
         'diet': 'first', 'body_PC1': 'mean', 'body_PC2': 'mean', 'LPJ_PC1': 'mean', 'LPJ_PC2': 'mean',
         'oral_PC1': 'mean', 'oral_PC2': 'mean', 'd15N': 'mean', 'd13C': 'mean'})
    targets = to_add_ronco.species
    to_add_ronco = to_add_ronco.drop(columns=['species', 'size_male', 'size_female'])
    pca_df = pca_df.reset_index().merge(to_add_ronco, how='left', on='FishID')
    pca_df['species'] = targets

    pca_df, df_key = replace_cat_with_nums(pca_df, col_names=['sex', 'habitat', 'diet'])
    pca_df = pca_df.dropna()
    targets = pca_df.species
    pca_df = pca_df.drop(columns=['species']).set_index('FishID')
    return pca_df, targets


def fish_fv_pca_df(feature_v, ronco_data):
    fv = feature_v.drop(columns=['parental_care', 'sociality', 'distribution', 'comments/links', 'size_male',
                                        'size_female', 'diet_contents', 'breeding', 'mouth_brooder', 'monogomous',
                                        'habitat_details', 'genome', 'tribe', 'notes', 'species_six', 'fish_n',
                                        'species_true', 'species_our_names', 'cluster'])

    combined = fv.merge(ronco_data.rename(columns={"sp": "six_letter_name_Ronco"}), 'left', on='six_letter_name_Ronco')
    ronco_to_fish = combined.groupby(['fish_ID'], as_index=False).agg(
        {'six_letter_name_Ronco': 'first', 'habitat': 'first',
         'diet': 'first', 'body_PC1': 'mean', 'body_PC2': 'mean', 'LPJ_PC1': 'mean', 'LPJ_PC2': 'mean',
         'oral_PC1': 'mean', 'oral_PC2': 'mean', 'd15N': 'mean', 'd13C': 'mean'})
    ronco_to_fish = ronco_to_fish.drop(columns=['six_letter_name_Ronco', 'habitat', 'diet'])
    pca_df_fv = fv.merge(ronco_to_fish, 'left', on='fish_ID')

    pca_df_fv, df_key = replace_cat_with_nums(pca_df_fv, col_names=['habitat', 'diet', 'cluster_pattern'])
    pca_df_fv = pca_df_fv.dropna()
    # drop undesired cols pf move and bout
    pca_df_fv = pca_df_fv.drop(columns=pca_df_fv.columns[pca_df_fv.columns.str.contains('move')])
    pca_df_fv = pca_df_fv.drop(columns=pca_df_fv.columns[pca_df_fv.columns.str.contains('bout')])

    # for species
    pca_df_fv_sp = pca_df_fv.groupby(by='six_letter_name_Ronco').mean()

    targets = pca_df_fv.six_letter_name_Ronco
    all_targets = pca_df_fv.loc[:, ['six_letter_name_Ronco', 'habitat', 'diet', 'cluster_pattern']]
    pca_df_fv = pca_df_fv.drop(columns=['six_letter_name_Ronco']).set_index('fish_ID')
    return pca_df_fv, targets, all_targets, df_key, pca_df_fv_sp


def run_pca(rootdir, data_input, n_com = 10):

    # check that there's no nans
    if np.max(np.max(data_input.isnull())):
        print('Some nulls in the data, cannot run')
        return

    # Standardizing the features -> is therefore covariance (if not scaled would be correlation)
    x = StandardScaler().fit_transform(data_input.values)
    mu = np.mean(data_input, axis=0)

    # run PCA
    pca = PCA(n_components=n_com)
    principalComponents = pca.fit_transform(x)
    labels = []
    for i in range(n_com):
        labels.append('pc{}'.format(i + 1))

    principalDf = pd.DataFrame(data=principalComponents, columns=labels)
    finalDf = pd.concat([principalDf, data_input.index.to_series().reset_index(drop=True)], axis=1)

    # reconstructing the fish series
    # https://stats.stackexchange.com/questions/229092/how-to-reverse-pca-and-reconstruct-original-variables-from-several-principal-com
    Xhat = np.dot(pca.transform(data_input)[:, :n_com], pca.components_[:n_com, :])
    Xhat += mu
    reconstructed = pd.DataFrame(data=Xhat, columns=data_input.columns)
    f, ax = plt.subplots(figsize=(10, 5))
    plt.plot(reconstructed)
    plt.savefig(os.path.join(rootdir, "reconstructed.png"), dpi=1000)
    plt.close()

    # plot reconstruction of pc 'n'
    plot_reconstruct_pc(rootdir, data_input, pca, mu, 1)

    # plot loadings of each pc
    loadings = plot_loadings(rootdir, pca, labels, data_input)

    # f, ax = plt.subplots(figsize=(10, 5))
    # plt.plot(reconstructed.loc[:, 'Astbur'])
    # plt.savefig(os.path.join(rootdir, "reconstructed_Astbur.png"), dpi=1000)
    # plt.close()

    return pca, labels, loadings, principalDf, finalDf, principalComponents


def replace_cat_with_nums(df, col_names):
    """ As categorical values can't be used for PCA, they are converted to numbers, also saves out the key
    (could improve the format but need to see how it's used)"""
    # first test if every column is there:
    for col in col_names:
        if not col in df.columns:
            print('missing column {}, take out?'.format(col))
            return

    df_i = copy.copy(df)
    col_vals_all = []
    col_nums_all = []
    for col in col_names:
        col_vals = df_i.loc[:, col].unique().tolist()
        col_nums = np.arange(len(df_i.loc[:, col].unique())).tolist()
        df_i[col].replace(col_vals, col_nums, inplace=True)
        col_vals_all.extend(col_vals)
        col_nums_all.extend(col_nums)
    d = {'col_vals': col_vals_all, 'col_nums': col_nums_all}
    df_key = pd.DataFrame(data=d)
    return df_i, df_key


if __name__ == '__main__':
    # Allows user to select top directory and load all als files here
    root = Tk()
    rootdir = askdirectory(parent=root)
    root.destroy()

    fish_tracks_bin, sp_metrics, tribe_col, species_full, fish_IDs, species_sixes = setup_run_binned(rootdir)
    feature_v, averages, ronco_data, cichlid_meta, diel_patterns, species = setup_feature_vector_data(rootdir)

    # get timings
    fps, tv_ns, tv_sec, tv_24h_sec, num_days, tv_s_type, change_times_s, change_times_ns, change_times_h, \
    day_ns, day_s, change_times_d, change_times_m, change_times_datetime, change_times_unit \
        = load_timings(fish_tracks_bin[fish_tracks_bin.FishID == fish_IDs[0]].shape[0])

    averages_vp, date_time_obj_vp, sp_vp_combined, averages_spd, sp_spd_combined, averages_rest, sp_rest_combined, \
    averages_move, sp_move_combined = plot_ridge_plots(fish_tracks_bin, change_times_datetime,
                                                       rootdir, sp_metrics, tribe_col)

    diel_patterns = load_diel_pattern(rootdir, suffix="*dp.csv")

    pca_df, targets = fish_bin_pca_df(fish_tracks_bin, ronco_data)
    pca_df_fv, targets, all_targets, df_key, pca_df_fv_sp = fish_fv_pca_df(feature_v, ronco_data)

    run_pca_df = pca_df_fv_sp
    pca, labels, loadings, principalDf, finalDf, principalComponents = run_pca(rootdir, run_pca_df)

    finalDf['target'] = run_pca_df.loc[:, 'cluster_pattern'].reset_index(drop=True)
    finalDf['species'] = run_pca_df.index.to_list()

    plot_variance_explained(rootdir, principalDf, pca)
    plot_2D_pc_space(rootdir, finalDf, target='target')
    plot_3D_pc_space(rootdir, finalDf)
    plot_factor_loading_matrix(rootdir, loadings, top_pc=3)
    pc_loadings_on_2D(rootdir, principalComponents[:, 0:2], np.transpose(pca.components_[0:2, :]), loadings, top_n=3)

    loadings = loadings.reset_index().rename(columns={'index': 'features'})
    pca_df = loadings.merge(diel_patterns, on='features')
    model, r_sq = run_linear_reg(pca_df.pc1, pca_df.day_night_dif)
    plt_lin_reg(rootdir, pca_df.pc1, pca_df.day_night_dif, model, r_sq)

    model, r_sq = run_linear_reg(pca_df.pc2, pca_df.peak)
    plt_lin_reg(rootdir, pca_df.pc2, pca_df.peak, model, r_sq)


