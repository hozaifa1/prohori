"""The physical ChArUco reference board. Single source of truth for its geometry."""
import cv2

SQUARES_X = 7
SQUARES_Y = 5
SQUARE_MM = 20.0
MARKER_MM = 15.0
DICTIONARY = cv2.aruco.DICT_5X5_100


def make_board() -> cv2.aruco.CharucoBoard:
    dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    # Board units are millimetres, so solvePnP translations come out in mm.
    return cv2.aruco.CharucoBoard((SQUARES_X, SQUARES_Y), SQUARE_MM, MARKER_MM, dictionary)
