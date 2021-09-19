#!/usr/bin/env python
# -*- coding: utf-8 -*-

import copy
import cv2
import numpy as np
from matplotlib import pyplot as plt
import time

from detect.Bump import BumpDetect
from detect.TrafficLight import TrafficDetect
from detect.StopLine import StopDetect

# from SensorData import SensorData
from helpers import *

class SelfDriver:
    def __init__(self, config):

        # constant variables
        self.IMAGE_WIDTH = config.get("image_width")
        self.IMAGE_HEIGHT = config.get("image_height")
        self.IMAGE_OFFSET = config.get("image_offset")
        self.IMAGE_GAP = config.get("image_gap")
        self.LANE_BIN_THRESHOLD = config.get("lane_bin_threshold")
        self.CAMERA_MATRIX = config.get("camera_matrix")
        self.DISTORTION_COEFFS = config.get("distortion_coeffs")
        self.CANNY_THRESHOLD_LOW = config.get("canny_threshold_low", 80)
        self.CANNY_THRESHOLD_HIGH = config.get("canny_threshold_high", 90)

        # 참고: cv2.getOptimalNewCameraMatrix
        # https://docs.opencv.org/3.3.0/dc/dbb/tutorial_py_calibration.html
        optimal_camera_matrix, optimal_camera_roi = cv2.getOptimalNewCameraMatrix(self.CAMERA_MATRIX, self.DISTORTION_COEFFS, (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 1, (self.IMAGE_WIDTH, self.IMAGE_HEIGHT))
        self.OPTIMAL_CAMERA_MATRIX = optimal_camera_matrix
        self.OPTIMAL_CAMERA_ROI = optimal_camera_roi

        # state definition
        # 0 끼어들기
        # 1 끼어들기 완료후 주행
        # 5 신호등
        # self.DrivingState = Enum("DrivingState", "none stop_line bump passenger")
        self.DRIVING_STATE_NONE = -1
        self.DRIVING_STATE_JOINT = 0
        self.DRIVING_STATE_NORMAL = 1
        self.DRIVING_STATE_TRAFFIC_LIGHT = 5
        self.DRIVING_STATE_STOP_LINE = 7
        self.DRIVING_STATE_BUMP = 8
        self.DRIVING_STATE_PASSENGER = 9
        self.DRIVING_STATE_ARPARKING = 10
        
        
        self.driving_state = 2



        # member variables
        self.sensor_data = None
        self.display_board = None
        self.image_helper = ImageHelper()
        self.lidar_helper = LidarHelper.LidarHelper()
        self.ultra_helper = UltraHelper()
        self.ar_helper = ArHelper()
        self.stop_detect = StopDetect()
        self.traffic_detect = TrafficDetect()
        self.bump_detect = BumpDetect()
        self.last_center = 300
        self.count = 0
        self.arNum = -1
        self.dist = -1
        self.start_time = 0
        self.lidar_front = 100
        self.cnt_right = 0

    def get_next_direction(self, sensor_data):

        # copy sensor deeply to make them synchronized throughout this function
        self.sensor_data = copy.deepcopy(sensor_data)

        # check correct image size
        if self.sensor_data.image is None:
            return 0, 0
        if not self.sensor_data.image.size == (640 * 480 * 3):
            return 0, 0

        image_size = (self.IMAGE_WIDTH, self.IMAGE_HEIGHT)
        image_dilated, image_undistorted = self.image_helper.img_processing(self.sensor_data.image, self.CAMERA_MATRIX, self.DISTORTION_COEFFS, self.OPTIMAL_CAMERA_MATRIX, self.OPTIMAL_CAMERA_ROI, image_size, self.CANNY_THRESHOLD_LOW, self.CANNY_THRESHOLD_HIGH)

        # perspective tranform
        Minv, warped = self.image_helper.warp_image(image_dilated, self.LANE_BIN_THRESHOLD)
        # cv2.imshow('warped2', warped)
        warped = cv2.cvtColor(warped,cv2.COLOR_GRAY2BGR)

        # show lidar in display_board
        if self.sensor_data.ranges:
            display_lidar = self.lidar_helper.lidar_visualizer(warped, self.sensor_data.ranges_left, self.sensor_data.ranges_right)
            self.display_board = display_lidar
            self.lidar_front = self.lidar_helper.lidar_front(self.sensor_data.ranges)
        else:
            print("no lidar_msg")
            
        if self.sensor_data.ar:
            self.arNum, self.dist = self.ar_helper.ArData(self.sensor_data.ar)
            print("arNum", self.arNum, "dist", self.dist)

        steer, speed = self.drive(warped, image_undistorted)

        # show ultra in display_board
        if self.sensor_data.ultra:
            image_size = (self.IMAGE_WIDTH, self.IMAGE_HEIGHT)
            display_ultra = self.ultra_helper.ultra_get(image_size, self.sensor_data.ultra)
            self.display_board = cv2.vconcat([self.display_board, display_ultra])
        else:
            print("no ultra_msg")

        return steer, speed


    def drive(self, image, image_undistorted):
        #cv2.imshow("image",image)
        print("state", self.driving_state)
        lpos, rpos = -1, -1
        for i in range(self.last_center, 640):
            if image[445][i][0] > 0:
                rpos = i
                break
        for i in range(self.last_center, -1, -1):
            if image[445][i][0] > 0:
                lpos = i
                break

        if lpos == -1 or rpos == -1:
            if rpos != -1:
                lpos = rpos -130
            elif lpos != -1:
                rpos = lpos + 130
            else:
                for i in range(self.last_center, 640):
                    if image[450][i][0] > 0:
                        rpos = i
                        break
                else:
                    rpos = 640

                for i in range(self.last_center, -1, -1):
                    if image[450][i][0] > 0:
                        lpos = i
                        break
                else:
                    lpos = 0


        # new_img = cv2.line(image,(0,445),(640,445), (0,0,255), 2)
        image.mean(axis=2)

        #480,640,3

        if rpos - lpos < 10:
            lpos, rpos = 220, 380

        elif rpos -lpos < 100:
            rpos = lpos + 130

        elif rpos - lpos > 600:
            lpos, rpos = 350, 520

        #########
        if self.driving_state == 0:
            llpos = -1
            for i in range(lpos - 50,-1,-1):
                if image[200][i][0] > 0:
                    llpos = i
                    break
            print("llpos", llpos)
            if 130>lpos - llpos >110 and llpos != -1 and self.count > 10:
                rpos = lpos
                lpos = llpos
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                self.driving_state = 1
                self.start_time = time.time()
                self.count = 0
        elif self.driving_state == 1 and self.sensor_data.ultra != None:
            print("ultra message")
            print(self.sensor_data.ultra[4], self.sensor_data.ultra[5])

          
            if self.sensor_data.ultra[4] <40 or self.sensor_data.ultra[5] < 40 and self.count > 10:
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!")
                lpos, rpos = 300,400
                self.driving_state = 0
                self.count = 0
            if time.time() - start_time >15:
                self.driving_state = 2




 
        ##나중에 지워야함

#        print("state",state)
#        print(lpos,rpos)
#        print(rpos-lpos)
#        print(" ")
        #############

        self.last_center = (rpos+lpos) // 2
        steer = int((self.last_center-300) // 2)
        speed = 15
        

        if self.driving_state == 2:
            #img, stopline_detected = self.stop_detect.stopline_det(image_undistorted)
            #cv2.imshow("img",img)
            #if stopline_detected:
                #angle = 0
                #speed = 0
                #print("stop line detected")
            traffic_sign = self.traffic_detect.traf_det(image_undistorted)
            if not traffic_sign:
                img, stopline_detected = self.stop_detect.stopline_det(image_undistorted)
                if stopline_detected:
                    angle = 0
                    speed = 0
                    print("stop line detected")
                    
            else:
                self.driving_state = 4
                self.start_time = time.time()
                
                
                
#        elif self.driving_state ==3:
#            if time.time()-self.start_time < 3:
#                speed = 15
#                angle = 0
#            elif time.time()-self.start_time < 6:
#                speed = 15
#                angle = 50
#            else:
#                self.driving_state = 4




        if self.arNum == 0 and self.dist < 0.6 and self.driving_state == 4:

            self.driving_state = 5
            self.start_time = time.time()
        elif self.driving_state == 5:
            t = 2.5
            if time.time() - self.start_time < t-0.1:
                speed = 15
                steer = 50
            elif time.time() - self.start_time < t + 1:
                speed = 0
                steeer = 0
            elif time.time() - self.start_time < 1.8*t + 1:
                speed = -20
                steer = -50
            elif time.time() - self.start_time < 2.3* t + 1:
                speed = -20
                steer = 50
            else:
                if self.dist > 0.8:
                    self.driving_state = 6
                    self.start_time = time.time()
                else:
                    speed = -20
                    steer = 0
        elif self.driving_state == 6:
            speed = 0
            steer = 0
            if 4 > time.time() - self.start_time > 3:
                speed = 15
                steer = -20
            elif 8> time.time() - self.start_time > 4:
                speed = 15
                steer = -40
            elif time.time() - self.start_time > 8:
                self.driving_state = 7
                self.start_time = time.time()
                self.last_center = 200
        
        elif self.driving_state == 7:
            if time.time() - self.start_time > 60:
                self.driving_state = 8
            print("it is yolo state")

        elif self.driving_state == 8:
            
            bump = self.bump_detect.bump_det(image_undistorted)
            if bump:
                self.driving_state = 9

        
        
        elif self.driving_state == 9:
            speed = 20
            steer = -2
            if self.lidar_front < 2.2:
                self.driving_state = 10
                self.start_time = time.time()
        elif self.driving_state == 10:
            speed = 0
            steer = -2
            self.cnt_right += len([x for x in self.sensor_data.ranges_right if 0 < x < 0.5])
            if self.cnt_right > 10 and time.time() - self.start_time > 2:
                self.driving_state = 11
                self.start_time = time.time()
                self.last_center = 300
                
        elif self.driving_state == 11:
            speed = 15
            if time.time() - self.start_time < 3:
                steer =20
            
            
            
            
        elif self.driving_state == 15 and self.sensor_data.ultra != None:
            if self.sensor_data.ultra[0] > 50:
                self.parallel_count += 1
            elif self.sensor_data.ultra[0] > 20:
                self.parallel_count = 0
            if self.parallel_count > 4:
                self.driving_state = 16
                self.start_time = time.time()
                
        elif self.driving_state == 16:
            if time.time() - self.start_time < 3.5:
                speed = 15
                steer = 0
            elif time.time() - self.start_time < 5:
                speed =-20
                steer = 50
            elif time.time() - self.start_time < 6:
                speed = -20
                steer = 0    
            elif time.time() - self.start_time < 7.5:
                speed = -20
                steer = -50     
            else:
                self.driving_state = 17            
        elif self.driving_state == 17:
            speed = 0
            steer = 0
            

        self.display_board = cv2.line(self.display_board,(self.last_center,445),(self.last_center,445),(255,0,0),30)
        self.display_board = cv2.line(self.display_board,(lpos,445),(lpos,445),(0,255,0),30)
        self.display_board = cv2.line(self.display_board,(rpos,445),(rpos,445),(0,255,0),30)



        self.count += 1
        return steer, speed


    def visualize(self):

        if self.display_board is not None:
            cv2.imshow("Sensor data display board", self.display_board)

        cv2.waitKey(1)
