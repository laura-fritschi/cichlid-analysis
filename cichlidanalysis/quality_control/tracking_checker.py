### this script loads a video and it's corresponding track, it plots the centroid over the video and allows you to scroll
# through and control the playback speed
# Inspiration from:
# https://stackoverflow.com/questions/54674343/how-do-we-create-a-trackbar-in-open-cv-so-that-i-can-use-it-to-skip-to-specific
# and for speed graph:
# https://stackoverflow.com/questions/32111705/overlay-a-graph-over-a-video

from tkinter import Tk
from tkinter.filedialog import askdirectory
import os
import sys
import glob

import cv2 as cv2
import numpy as np
import matplotlib.pyplot as plt

from cichlidanalysis.io.meta import load_yaml, extract_meta
from cichlidanalysis.io.tracks import extract_tracks_from_fld, get_file_paths_from_nums
from cichlidanalysis.analysis.processing import interpolate_nan_streches, remove_high_spd_xy, smooth_speed


def tracker_checker_inputs(video_path_i):
    """ Get the inputs for the tracker_checker

    :param video_path_i:
    :return:
    """
    vid_folder_path = os.path.split(video_path_i)[0]
    vid_timestamp = os.path.split(video_path_i)[1][0:-10]
    cam_folder_path = os.path.split(vid_folder_path)[0]
    vid_folder = os.path.split(vid_folder_path)[1]

    track_single_i, displacement_internal = extract_tracks_from_fld(vid_folder_path, vid_timestamp)
    vid_name = os.path.split(video_path_i)[1]

    meta = load_yaml(vid_folder_path, "meta_data")
    config = load_yaml(cam_folder_path, "config")
    fish_data = extract_meta(vid_folder)

    new_rois = load_yaml(vid_folder_path, "roi_file")
    rois = load_yaml(cam_folder_path, "roi_file")

    # This if statement checks if there is a new background associated with the video and loads it instead
    # Also needs to be able to deal with multiple background files (if the video was split by divide_tracking.py)
    os.chdir(vid_folder_path)
    video_folder_files = glob.glob(vid_timestamp + "*background.png")
    if len(video_folder_files) > 0:
        print('using background made from video')
        if os.path.isfile(os.path.join(vid_folder_path, video_folder_files[0])):
            previous_bgd_name = video_folder_files
            print(previous_bgd_name)

            if len(previous_bgd_name) != 1:
                print('more than 1 background files detected:' + cam_folder_path)
                background_full = []  # Make this a dictionary instead of a list, so it can be named? Or carry over previous_bgd_name
                for file in previous_bgd_name:
                    background_path = os.path.join(vid_folder_path, "{}".format(file))
                    background_full.append(cv2.imread(glob.glob(background_path)[0], 0))
                # Need to modify them if new roi exists but background comes from
                os.chdir(cam_folder_path)
                bkgd = background_full
            else:
                background_path = os.path.join(vid_folder_path, "{}".format(previous_bgd_name[0]))
                background_full = cv2.imread(glob.glob(background_path)[0], 0)
                os.chdir(cam_folder_path)
                bkgd = background_full
                # # if new roi and background is from video then skip this
                # if bool(new_rois):
                #     roi_n = new_rois["roi_" + fish_data['roi'][1]]
                #     bkgd = background_full[roi_n[1]:roi_n[1] + roi_n[3], roi_n[0]:roi_n[0] + roi_n[2]]
                # else:
                #     bkgd = background_full
        else:
            print("weird exit not sure why")
            sys.exit()
    else:
        print('using background made from full recording image')
        os.chdir(cam_folder_path)
        files = glob.glob("*.png")
        files.sort()
        files.insert(0, files.pop(files.index(min(files, key=len))))
        if "{}_Median.png".format(vid_timestamp) in files:
            previous_bgd_name = files[files.index("{}_Median.png".format(vid_timestamp)) - 1]
            print(previous_bgd_name)
        else:
            previous_bgd_name = files[files.index("{}_per90_Background.png".format(vid_timestamp)) - 1]
            print(previous_bgd_name)

        # find and load background file
        background_path = os.path.join(cam_folder_path, "{}".format(previous_bgd_name))
        if len(glob.glob(background_path)) != 1:
            print('too many or too few background files in folder:' + cam_folder_path)
            sys.exit()
        else:
            background_full = cv2.imread(glob.glob(background_path)[0], 0)
        os.chdir(cam_folder_path)
        roi_n = rois["roi_" + fish_data['roi'][1]]
        bkgd = background_full[roi_n[1]:roi_n[1] + roi_n[3], roi_n[0]:roi_n[0] + roi_n[2]]

    os.chdir(cam_folder_path)
    roi_n = rois["roi_" + fish_data['roi'][1]]
    # interpolate between NaN streches
    try:
        x_n = interpolate_nan_streches(track_single_i[:, 1])
        y_n = interpolate_nan_streches(track_single_i[:, 2])
    except:
        x_n = track_single_i[:, 1]
        y_n = track_single_i[:, 2]

    if new_rois:
        # subtract the difference so that the centroids are plotted at the right coordinates
        # output: (x,y,w,h)
        # assume that if there is a new ROI, there is only one.
        x_n += new_rois['roi_{}'.format('0')][0]
        y_n += new_rois['roi_{}'.format('0')][1]
        track_single_i[:, 1] += new_rois['roi_{}'.format('0')][0]
        track_single_i[:, 2] += new_rois['roi_{}'.format('0')][1]
        roi_n = new_rois['roi_{}'.format('0')]

        # add in ROI to video
        start_point = (roi_n[0], roi_n[1])
        end_point = (roi_n[0] + roi_n[2], roi_n[1] + roi_n[3])
    else:
        start_point = (0, 0)
        end_point = (roi_n[2], roi_n[3])

    # find displacement
    displacement_i_mm_s = displacement_internal * config["mm_per_pixel"] * config['fps']
    speed_full_i = np.sqrt(np.diff(x_n) ** 2 + np.diff(y_n) ** 2)
    speed_t, x_nt_i, y_nt_i = remove_high_spd_xy(speed_full_i, x_n, y_n)

    spd_sm = smooth_speed(speed_t, win_size=5)
    spd_sm_mm = spd_sm * config["mm_per_pixel"]
    spd_sm_mm_ps = spd_sm_mm * config['fps']

    thresh = 15

    # Make a list of ranges, by extracting it from the previous_median_name (s)
    if isinstance(previous_bgd_name, list) and len(previous_bgd_name) > 1:
        pmn = []
        for file in previous_bgd_name:
            # only want split and divided backgrounds (not remade backgrounds)
            if 'frame' in file:
                pmn.append(np.arange(int(file.split("_")[4][5:9:]), int(file.split("_")[4][11:16:])))
    else:
        pmn = previous_bgd_name

    return bkgd, pmn, spd_sm, spd_sm_mm_ps, thresh, displacement_i_mm_s, vid_name, track_single_i, start_point, end_point, \
           x_nt_i, y_nt_i


# # function called by trackbar, sets the next frame to be read
def get_frame(frame_nr, video):
    # global video
    video.set(cv2.CAP_PROP_POS_FRAMES, frame_nr)


def track_checker_gui(video_path_j, bgd, pmn, spd_sm, spd_sm_mm_ps, thresh, displacement_i_mm_s,
                      vid_name, track_single_i, start_point, end_point, x_nt, y_nt):
    """ this script loads a video and it's corresponding track, it plots the centroid over the video and allows you to
    scroll through the video. Prints the ROI if it is in the video folder (indidcating a new ROI).

    :param video_path_j:
    :param bgd:
    :param pmn:
    :param spd_sm:
    :param spd_sm_mm_ps:
    :param thresh:
    :param displacement_i_mm_s:
    :param vid_name:
    :param track_single_i:
    :param start_point:
    :param end_point:
    :param x_nt:
    :param y_nt:
    :return:
    """
    # open video
    video = cv2.VideoCapture(video_path_j)

    # get total number of frames
    nr_of_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    # create display window
    cv2.namedWindow("Speed of {}".format(vid_name))
    cv2.namedWindow("Background subtraction of {}".format(vid_name))

    # add track bar
    cv2.createTrackbar("Frame", "Speed of {}".format(vid_name), 0, nr_of_frames, lambda f: get_frame(f, video))

    ret, frame = video.read()
    # height, width = frame.shape[:2]
    frame_bw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if isinstance(bgd, list):
      if frame_bw.shape != bgd[0].shape:
          for file in bgd:
              if frame_bw.shape != file.shape:
                  # add padding to the median
                  if frame_bw.shape[0] != file.shape[0] and frame_bw.shape[1] == file.shape[1]:
                      file = np.concatenate((file, frame_bw[file.shape[0]:frame_bw.shape[0], :]), axis=0)

                  if frame_bw.shape[0] == file.shape[0] and frame_bw.shape[1] != file.shape[1]:
                      file = np.concatenate((file, frame_bw[:, file.shape[1]:frame_bw.shape[1]]), axis=1)

          print("frame_bw shape doesn't equal the shape of the first of multiple background images")
          sys.exit()
    if isinstance(bgd, (np.ndarray, np.generic)):
        if frame_bw.shape != bgd.shape:
            # add padding to the median
            if frame_bw.shape[0] != bgd.shape[0] and frame_bw.shape[1] == bgd.shape[1]:
                bgd = np.concatenate((bgd, frame_bw[bgd.shape[0]:frame_bw.shape[0], :]), axis=0)

            if frame_bw.shape[0] == bgd.shape[0] and frame_bw.shape[1] != bgd.shape[1]:
                bgd = np.concatenate((bgd, frame_bw[:, bgd.shape[1]:frame_bw.shape[1]]), axis=1)

    # max_sp = int(np.nanpercentile(speed_sm, 99) + 5)
    max_sp = np.nanmax(spd_sm_mm_ps)
    fig, ax = plt.subplots()
    plt.ion()
    plt.show()
    playing = 1

    while 1:
        # show frame, break the loop if no frame is found
        curr_frame = video.get(cv2.CAP_PROP_POS_FRAMES) - 1

        if ret:
            try:
                cX, cY = (int(track_single_i[int(curr_frame), 1]), int(track_single_i[int(curr_frame), 2]))
                cv2.circle(frame, (int(x_nt[int(curr_frame)]), int(y_nt[int(curr_frame)])), 4, (0, 255, 255), 4)
                cv2.circle(frame, (cX, cY), 4, (0, 0, 255), 2)
                cv2.putText(frame, "yellow: corrected centroid, red: raw centroid, frame: {}".format(curr_frame),
                            (5, 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 200), 1)
                cv2.rectangle(frame, start_point, end_point, 220, 2)
            except:
                cv2.rectangle(img=frame, pt1=(0, 0), pt2=(10, 10), color=(0, 0, 255), thickness=-1)

            cv2.imshow("Speed of {}".format(vid_name), frame)
            frame_bw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # find background which is in the right range
            if isinstance(bgd, list):
                pmn_index = []
                for i in pmn:
                    pmn_index.append(curr_frame in i)
                frame_delta = cv2.absdiff(frame_bw, bgd[np.where(pmn_index)[0][0]])
            else:
                frame_delta = cv2.absdiff(frame_bw, bgd)
            image_thresholded = cv2.threshold(frame_delta, 35, 255, cv2.THRESH_TOZERO)[1]
            (contours, _) = cv2.findContours(image_thresholded.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(contours) > 0:
                contourOI_ = (max(contours, key=cv2.contourArea))
                area = cv2.contourArea(contourOI_)
                if area > 100:
                    contourOI = (cv2.convexHull(contourOI_))
                cv2.drawContours(frame_delta, contourOI_.astype(int), -1, 255, 1)

            frame_delta = cv2.cvtColor(frame_delta, cv2.COLOR_GRAY2BGR)
            try:
                cv2.circle(frame_delta, (int(x_nt[int(curr_frame)]), int(y_nt[int(curr_frame)])), 4, (0, 255, 255), 4)
                cv2.circle(frame_delta, (cX, cY), 4, (0, 0, 255), 2)
            except:
                cv2.rectangle(img=frame, pt1=(0, 0), pt2=(10, 10), color=(0, 0, 255), thickness=-1)

            cv2.rectangle(frame_delta, start_point, end_point, 220, 2)
            cv2.imshow("Background subtraction of {}".format(vid_name), frame_delta)

        ax.clear()
        dummy = np.zeros([int(max_sp), 400, 3]).astype(np.uint8)
        plt.imshow(dummy, origin='lower')

        if curr_frame > 200:
            track_curr = 200
        else:
            track_curr = curr_frame
        plt.plot([track_curr, track_curr], [-0.01, max_sp], color='r')

        win_min = int(curr_frame - 20 * 10)
        win_max = int(curr_frame + 20 * 10)

        if win_min < 0:
            win_min = 0
        if win_max > spd_sm.shape[0]:
            win_max = spd_sm.shape[0]

        values = spd_sm_mm_ps[win_min:win_max]
        values_2 = displacement_i_mm_s[win_min:win_max]
        plt.plot(values_2)
        plt.plot(values, linewidth=3)
        # plt.plot([0, 400], [thresh, thresh])
        plt.plot([0, 400], [15, 15])

        ax.set_ylim([0, max_sp])
        ax.set_xlim([0, 400])
        ax.set_aspect('auto')
        # ax.legend(["current frame", "speed_sm_mm_ps", "thresh 15mm/s"])
        ax.legend(["current frame", "speed_raw_mm_ps", "speed_sm_mm_ps", "threshold {}".format(thresh)])
        plt.ylabel("mm/s")

        k = cv2.waitKey(33)
        # stop playback when q is pressed
        if k == 27 or k == ord("q"):
            cv2.destroyAllWindows()
            break
        elif k == 32:
            if playing == 0:
                playing = 1
            elif playing == 1:
                playing = 0

        elif k == ord("a"):
            frame_nr = video.get(cv2.CAP_PROP_POS_FRAMES)
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_nr - 2)
            ret, frame = video.read()

        elif k == ord("d"):
            frame_nr = video.get(cv2.CAP_PROP_POS_FRAMES)
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_nr)
            ret, frame = video.read()

        elif k == ord("n"):
            # release resources
            plt.close()
            video.release()
            cv2.destroyAllWindows()
            return True

        if playing:
            # Get the next videoframe
            ret, frame = video.read()
        else:
            ret = True

    # release resources
    video.release()
    cv2.destroyAllWindows()
    return False


def run_tracker_checker():
    """ For running the tracker checker. Allows you to define the movie number and folder

    :return:
    """
    # define movie number to check
    video_num = '-1'
    while int(video_num) == -1:
        video_num = input("What is the number of the movie you would like to check?:")

    # Allows a user to select folder138
    root = Tk()
    video_folder_path = askdirectory(parent=root, title="Select movie file")
    root.destroy()

    video_path = get_file_paths_from_nums(video_folder_path, video_num, file_format='*.mp4')
    if len(video_path):
        video_path = video_path[0]
    else:
        print("Couldn't find the movie. Exiting")
        return

    next_vid = True

    while next_vid is True:
        background, previous_bgd_name, speed_sm, speed_sm_mm_ps, threshold, displacement_internal_mm_s, video_name, \
        track_single, s_point, e_point, x_nt, y_nt = tracker_checker_inputs(video_path)

        next_vid = track_checker_gui(video_path, background, previous_bgd_name, speed_sm, speed_sm_mm_ps, threshold,
                                     displacement_internal_mm_s,
                                     video_name, track_single, s_point, e_point, x_nt, y_nt)
        next_movie_n = "_" + str(int(video_path.split('_')[-2]) + 1).zfill(len(video_path.split('_')[-2])) + "_"

        os.chdir(os.path.split(video_path)[0])
        video_files = glob.glob("*.mp4")
        for vid in video_files:
            if next_movie_n in vid:
                video_path = os.path.join(os.path.split(video_path)[0], vid)


if __name__ == '__main__':
    run_tracker_checker()
