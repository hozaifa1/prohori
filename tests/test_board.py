import cv2

from prohori.board import SQUARES_X, SQUARES_Y, make_board


def test_board_round_trip():
    board = make_board()
    img = board.generateImage((1400, 1000), marginSize=40, borderBits=1)
    corners, ids, _, _ = cv2.aruco.CharucoDetector(board).detectBoard(img)
    assert ids is not None and len(ids) == (SQUARES_X - 1) * (SQUARES_Y - 1)
