# This file will ask you to load a movie, and allow you to scroll through.
# Then you can measure the standard length of the fish.
# it will then ask you to draw the length of the fish 3 times.
# It will take the average length and add this to the meta file
import os
from tkinter.filedialog import askopenfilename
from tkinter import *

import cv2 as cv2
import numpy as np
import yaml

from cichlidanalysis.io.meta import load_yaml, add_sex
from cichlidanalysis.measuring.measure_units import measuring


def getFrame(frame_nr):
    """function called by trackbar, sets the next frame to be read
    """
    # global video
    video.set(cv2.CAP_PROP_POS_FRAMES, frame_nr)


def main():
    # Allows a user to select a directory of movie
    root = Tk()
    root.withdraw()
    root.update()
    filepath = askopenfilename(title="Select movie file", filetypes=(("mp4 files", "*.mp4"), ("all files", "*.*")))
    root.destroy()

    parts = os.path.split(filepath)
    add_sex(parts[0])
    meta = load_yaml(parts[0], "meta_data")

    # check if fish has already been measured or not
    if 'fish_length_mm' in meta:
        remeasure = 'm'
        while remeasure not in {'y', 'n'}:
            remeasure = input("Fish has already been measured and the length is {}. Do you want to overwrite this "
                              "measurement? y/n \n".format(meta["fish_length_mm"]))
        if remeasure == 'n':
            print("Leaving previous measurement")
            return
        else:
            print("making new measurement")

    # check if pixel units have already been measured for this camera or not
    partss = os.path.split(parts[0])
    config_file = load_yaml(partss[0], "config")

    if 'mm_per_pixel' not in config_file:
        print("No mm_per_pixel, use script: Measure_Units")
        return

    # load video
    global video
    video = cv2.VideoCapture(filepath)
    nr_of_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    # set up image display and trackbar for
    cv2.namedWindow('Measuring fish length')
    cv2.createTrackbar("Frame", "Measuring fish length", 0, nr_of_frames, getFrame)

    playing = 1

    while video.isOpened():
        # Get the next videoframe
        if playing:
            ret, frame = video.read()
            cv2.putText(frame, "Press enter to select frame, press space bar to pause", (5, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (10, 10, 200), 2)

        cv2.imshow("Measuring fish length", frame)
        k = cv2.waitKey(100) & 0xff

        if k == 27:
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

        elif k == 32:
            if playing == 0:
                playing = 1
            elif playing == 1:
                playing = 0

        elif k == 13:
            line_length_pixels = measuring(frame)

            fish_lengths_mm = line_length_pixels * config_file["mm_per_pixel"]
            fish_length_mm = round(np.mean(fish_lengths_mm), 0)

            print("rounding fish length to closest mm \n fish_length_mm: {}".format(fish_length_mm))
            meta["fish_length_mm"] = fish_length_mm.item()

            with open(os.path.join(parts[0], "meta_data.yaml"), "w") as file:
                documents = yaml.dump(meta, file)
            break

    # release resources
    video.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
