#!/bin/bash
sleep 30
/usr/bin/screen -d -m /usr/bin/python /home/pi/cherry/cherry.py
sleep 5
midori -e Fullscreen -a 127.0.0.1:8080/mini
