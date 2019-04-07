#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Voltage Monitor: a small example on how to use a Yocto-Volt usb module
"""

# import standard functions
import cherrypy
import string
import sys
import os, os.path
import threading
import json
import smtplib
import socket
from optparse import OptionParser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEImage import MIMEImage
from cherrypy.lib import file_generator

# import Yoctopuce Python library (installed form PyPI)
from yoctopuce.yocto_api import *
from yoctopuce.yocto_voltage import *
import matplotlib

# force matplotlib do not use any Xwindow backend
matplotlib.use('Agg')
import matplotlib.pyplot as plt

Options = None
MyIP = ""
AllSensors = {}

class MainPage(object):
    @cherrypy.expose
    def index(self):
        return open('public/html/index.html')
    
    @cherrypy.expose
    def mini(self):
        return open('public/html/mini.html')
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def sensor_list(self, **params):
        res = []               
        for sid in AllSensors:
            sensor = AllSensors[sid]
            res.append({"id": sensor.getID(), "name": sensor.getName()})

        # Responses are serialized to JSON (because of the json_out decorator)
        return res

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def status(self):
        start = datetime.datetime.today()
        input_json = cherrypy.request.json
        recorder = AllSensors.itervalues().next()
        ip = cherrypy.request.headers["Remote-Addr"]
        
        if recorder.check_key(input_json, "sens"):
            sens = str(input_json["sens"])
            recorder = AllSensors[sens]
            
            if recorder.check_key(input_json, "ip_in_control"):
                ip_in_control = str(input_json["ip_in_control"])
                recorder.set_ip_in_control(ip_in_control)
                
            if ip != recorder._ip_in_control:
                return recorder.getStatus(ip)
                
            if recorder.check_key(input_json, "sens"):
                sens = str(input_json["sens"])
                recorder = AllSensors[sens]
   
            if recorder.check_key(input_json, "target_value"):
                target_value = float(input_json["target_value"])
                recorder.set_target_value(target_value)
                
            if recorder.check_key(input_json, "method_to_use"):
                check_method = str(input_json["method_to_use"])
                recorder.set_method_to_use(check_method)
                
            if recorder.check_key(input_json, "type_of_check"):
                check_type = str(input_json["type_of_check"])
                recorder.set_type_of_check(check_type)
                
            if recorder.check_key(input_json, "enabled"):
                enabled = eval(str(input_json["enabled"]))
                recorder.set_enabled(enabled)
                
            if recorder.check_key(input_json, "stop_when_target_reached"):
                enabled = eval(str(input_json["stop_when_target_reached"]))
                recorder.set_stop_when_target_reached(enabled)
                
            if recorder.check_key(input_json, "recording"):
                recording = eval(str(input_json["recording"]))
                recorder.toggle_record(recording)
                
            if recorder.check_key(input_json, "email"):
                tmp = str(input_json["email"])
                if tmp != "":
                    recorder.set_email(tmp)

            # Return our current status of all variables
            return recorder.getStatus(ip)

def SendEmail(strFrom, strTo, msgRoot):
    if Options.verbose:
        print("Send email from %s to %s with SMPT info: %s:%d (%s:%s)" % (
            strFrom, strTo, Options.mail_host, Options.mail_port, Options.mail_user, Options.mail_pass))
    mailServer = smtplib.SMTP(Options.mail_host, Options.mail_port)
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    if Options.mail_user != "":
        mailServer.login(Options.mail_user, Options.mail_pass)
    mailServer.sendmail(strFrom, strTo, msgRoot.as_string())
    mailServer.close()
    if Options.verbose:
        print("Email successfully sent.")

def SendWelcomeEmail():
    # Create the body of the message (a plain-text and an HTML version).
    base_link = "http://%s:%d" % (MyIP, Options.http_port)
    link = base_link + "/"
    text = "Hi!\n The Voltage Monitor v1.0 has been started\n\nYou can start the monitoring with the following link\n%s" \
           % link
    f = open("public/html/welcomemail.html")
    html = f.read()
    html = html.replace("YYYSERVERYYY", base_link)
    f.close()
    # Create the root message and fill in the from, to, and subject headers
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = "Voltage Monitor Started "
    msgRoot.preamble = 'This is a multi-part message in MIME format.'
    # Encapsulate the plain and HTML versions of the message body in an
    # 'alternative' part, so message agents can decide which they want to display.
    msgAlternative = MIMEMultipart('alternative')
    msgRoot.attach(msgAlternative)
    msgText = MIMEText(text)
    msgAlternative.attach(msgText)
    # We reference the image in the IMG SRC attribute by the ID we give it below
    msgText = MIMEText(html, 'html')
    msgAlternative.attach(msgText)
    SendEmail(Options.email, Options.email, msgRoot)

class voltage_recorder(threading.Thread):
    def __init__(self, sensor, defaultEmail):
        threading.Thread.__init__(self)
        self.daemon = True
        self._volt_sensor = sensor
        self._last_value = YVoltage.CURRENTVALUE_INVALID
        self._email = defaultEmail   
        self._type_of_check = "voltage"
        self._method_to_use = "higher than"
        self._target_value = 250       
        self._lock = threading.Lock()
        self._target_reached = False
        self._ip_in_control = "0.0.0.0"
        self._recording_data_x = []
        self._recording_data_y = []
        self._recording_data_label_x = []
        self._recording_data_label_y = []
        self._highest_value = 0
        self._highest_value_last_recorded = datetime.datetime.today()
        self._plot_file_location = "public/images/plot.%s.png" % self._volt_sensor.get_hardwareId()
        self._mini_plot_file_location = "public/images/miniplot.%s.png" % self._volt_sensor.get_hardwareId()
        self._current_module = -1
        self._highest_value_start_time = datetime.datetime.today()
        self._last_recorded = datetime.datetime.today()
        self._graph_resolution = 1
        self._current_recording_stage = 1
        self._recording_loop_helper = 0
        self._recording = False   
        self._last_plot_size = -1
        self._enabled = False
        self._stopwatch = 0
        self._module_recording_status = ""
        self._stop_when_target_reached = False

    def check_key(self, dict, key):    
        if key in dict.keys(): 
            return True
        else: 
            return False
        
    def getName(self):
        return self._volt_sensor.get_friendlyName()

    def getID(self):
        return self._volt_sensor.get_hardwareId()
    
    def set_target_value(self, target_value):
        if target_value != self._target_value:
            print("%s set target to %s" % (self.getName(), target_value))
        self._target_value = target_value

    def set_ip_in_control(self, ip_in_control):
        if ip_in_control != self._ip_in_control:
            print("%s set ip in control to %s" % (self.getName(), ip_in_control))
        self._ip_in_control = ip_in_control
        
    def set_type_of_check(self, type_of_check):
        if type_of_check != self._type_of_check:
            print("%s set type_of_check to %s" % (self.getName(), type_of_check))
        self._type_of_check = type_of_check

    def set_method_to_use(self, method_to_use):
        if method_to_use != self._method_to_use:
            print("%s set method_to_use to %s" % (self.getName(), method_to_use))
        self._method_to_use = method_to_use

    def set_stop_when_target_reached(self, enabled):
        if enabled != self._stop_when_target_reached:
            print("%s set stop_when_target_reached to %s" % (self.getName(), enabled))
        self._stop_when_target_reached = enabled  
        
    def set_enabled(self, enabled):
        if enabled != self._enabled:
            print("%s set enabled to %s" % (self.getName(), enabled))
        self._enabled = enabled  
    
    def set_email(self, email):
        if email != self._email:
            print("%s set email to %s" % (self.getName(), email))
        self._email = email

    def toggle_record(self, status):
        if status == True:
            if self._recording:
                return
            msg = "%s Start recording" % self.getName()
            print(msg)
            self._target_reached = False
            self._recording_data_x = []
            self._recording_data_y = []
            self._recording_data_label_x = []
            self._recording_data_label_y = []
            self._recording_start_time = datetime.datetime.today()
            self._last_recorded = datetime.datetime.today()
            self._highest_value = 0
            self._graph_resolution = 5
            self._module_recording_status = "starting"
            self._recording = True
            if self._method_to_use == "test":
                self._current_module = 1
            self._stopwatch = 0
            self._module_recording_status = "disabled"
            if self._method_to_use != "test":
                self.plot_graph()       
                self.sendResult(msg, self._last_value)
        elif status == False:
            if not self._recording:
                return
            msg = "Stop voltage recording for %s" % self.getName()
            print(msg)
            self._recording = False
            self._stopwatch = 0
            self._current_module = -1
            self._recording_loop_helper = 0
            self._current_recording_stage = 1
            self.plot_graph()
            self.sendResult(msg, self._last_value)

    def checkTargetValue(self, method, last_value, target_value, last_recorded_time, recording_start_time, highest_value_last_recorded):
        if method == "higher than":
            if last_value >= target_value:
                return True
        
        elif method == "lower than":
            if last_value <= target_value:
                return True
                
        elif method == "highest value for":
            delta = datetime.datetime.today() - highest_value_last_recorded
            minutes = delta.total_seconds() / 60
            
            if minutes >= target_value:
                return True
            
        elif method == "elapsed for":
            if last_recorded_time >= recording_start_time + datetime.timedelta(minutes=target_value):
                return True
                
        elif method == "test":
            if last_recorded_time >= recording_start_time + datetime.timedelta(minutes=target_value):
                return True
                
        return False
                
    def add_new_value(self, voltage, label=False, force=False):
        global Options
        now = datetime.datetime.today()
        delta = now - self._last_recorded
        if delta.total_seconds() > self._graph_resolution or force:
            if Options.verbose:
                print("%s add new value (%d)" % (self.getName(), voltage))
                
            # Check to see if highest value has been set yet -- set it if not
            if self._highest_value != 0:
                high_volts = self._highest_value + .5
                low_volts = self._highest_value - .5

                # if voltage is within a tolerance of +- .5 of recorded highest voltage, keep it
                if voltage > high_volts or voltage < low_volts:
                    if Options.verbose:
                        print("Set a new highest value: %s" % voltage)
                    self._highest_value = voltage
                    self._highest_value_last_recorded = now
                    
            # Set initial highest value     
            elif self._highest_value == 0:
                if Options.verbose:
                    print("Set a new highest value: %s" % voltage)
                self._highest_value = voltage
                self._highest_value_last_recorded = now
                
            from_start_time = now - self._recording_start_time
            from_start_minutes = from_start_time.total_seconds() / 60
            from_start_hours = round(from_start_time.total_seconds() / 3600, 2)
            self._recording_data_y.append(voltage)
            self._recording_data_x.append(from_start_minutes)
            if label:
                self._recording_data_label_y.append(voltage)
                self._recording_data_label_x.append(from_start_minutes)
            self._last_recorded = now
            if len(self._recording_data_y) == 200:
                new_resolution = self._graph_resolution * 2
                if Options.verbose:
                    print(
                        "%s increase graph interval (%d to %d)" % (
                            self.getName(), self._graph_resolution, new_resolution))
                new_x = []
                new_y = []
                for i in range(0, len(self._recording_data_y), 2):
                    y = (self._recording_data_y[i] + self._recording_data_y[i + 1]) / 2
                    x = (self._recording_data_x[i] + self._recording_data_x[i + 1]) / 2
                    new_x.append(x)
                    new_y.append(y)
                self._recording_data_x = new_x
                self._recording_data_y = new_y
                self._graph_resolution = new_resolution
            self.plot_graph()

    def getStatus(self, ip):
        return {
            'voltage': self._last_value,
            'email': self._email,
            'recording': self._recording,
            'stopwatch': self._stopwatch,
            'type_of_check': self._type_of_check,
            'method_to_use': self._method_to_use,
            'target_value': self._target_value,
            'stop_when_target_reached': self._stop_when_target_reached,
            'enabled': self._enabled,
            'current_module': self._current_module,
            'module_recording_status': self._module_recording_status,
            'ip_in_control': self._ip_in_control,
            'your_ip': ip
        }

    def plot_graph(self):
        global Options
        self._lock.acquire()
        if self._last_plot_size == len(self._recording_data_y):
            self._lock.release()
            return
        start = datetime.datetime.today()
        self._last_plot_size = len(self._recording_data_y)
        
        plt.rcParams['xtick.direction'] = 'in'
        plt.rcParams['ytick.direction'] = 'in'
        
        fig1 = plt.figure(figsize=(12,6))
        
        plt.minorticks_on()
        plt.margins(x=0)
        plt.gcf().subplots_adjust(left=0.07, right=0.93, bottom=0.08, top=0.99)
		
        sp = fig1.add_subplot(111)
        sp.plot(self._recording_data_x, self._recording_data_y, color="red")
        sp.set_ylabel("Voltage")
        sp.set_xlabel("Time (minutes)")
        
        for i,j in zip(self._recording_data_label_x, self._recording_data_label_y):
            sp.annotate('%sV' %j, xy=(i,j), xytext=(5,0), textcoords='offset points')

        fig1.savefig(self._plot_file_location)
        
        fig2 = plt.figure(figsize=(4.7, 2.6))
        
        plt.minorticks_on()
        plt.margins(x=0)
        plt.gcf().subplots_adjust(left=0.005, right=0.85, bottom=0.15, top=0.99)
        
        sp2 = fig2.add_subplot(111)
        sp2.tick_params(axis='both', which='major', labelsize=7)
        sp2.tick_params(axis='both', which='minor', labelsize=7)
        sp2.plot(self._recording_data_x, self._recording_data_y, color="red")
        sp2.yaxis.set_label_position("right")
        sp2.yaxis.tick_right()
        sp2.set_ylabel("Voltage")
        sp2.set_xlabel("Time (minutes)")
        
        for i,j in zip(self._recording_data_label_x, self._recording_data_label_y):
            sp2.annotate('%sV' %j, xy=(i,j), xytext=(5,0), textcoords='offset points')

        fig2.savefig(self._mini_plot_file_location)
        
        if self._current_module > -1:
            current_module = "public/images/plot.%s-MODULE-%s.png" % (self._volt_sensor.get_hardwareId(), self._current_module)
            fig1.savefig(current_module)

            if Options.verbose:
                print("saving current module: %s" % self._current_module)
            
        fig1.clf()
        fig2.clf()
        plt.close('all')
        if Options.verbose:
            delta = datetime.datetime.today() - start
            print("%s: PLOT graph rendering took %d seconds for %d points"
                  % (self.getName(), delta.total_seconds(), self._last_plot_size))
        self._lock.release()

    def sendResult(self, title, voltage):
        # me == my email address
        global Options
        global MyIP
        if self._email == "":
            return
        print("SENDING EMAIL")
        # Define these once; use them twice!
        strFrom = self._email
        strTo = self._email
        # Create the body of the message (a plain-text and an HTML version).
        base_link = "http://%s:%d" % (MyIP, Options.http_port)
        link = base_link + "/"
        text = "Hi!\n%s\n\nYou can see the voltage graph with the following link\n%s" % (title, link)
        f = open("public/html/mail.html")
        html = f.read()
        html = html.replace("YYYMSGYYY", title)
        html = html.replace("YYYSERVERYYY", base_link)
        html = html.replace("YY000YY", "current value is %2.1f" % voltage)
        f.close()
        # Create the root message and fill in the from, to, and subject headers
        msgRoot = MIMEMultipart('related')
        msgRoot['Subject'] = "Voltage Monitor: " + title
        msgRoot['From'] = strFrom
        msgRoot['To'] = strTo
        msgRoot.preamble = 'This is a multi-part message in MIME format.'

        # Encapsulate the plain and HTML versions of the message body in an
        # 'alternative' part, so message agents can decide which they want to display.
        msgAlternative = MIMEMultipart('alternative')
        msgRoot.attach(msgAlternative)

        msgText = MIMEText(text)
        msgAlternative.attach(msgText)

        # We reference the image in the IMG SRC attribute by the ID we give it below
        msgText = MIMEText(html, 'html')
        msgAlternative.attach(msgText)

        # This example assumes the image is in the current directory
        fp = open(self._plot_file_location, 'rb')
        img = fp.read()
        print("img size= %d" % len(img))
        msgImage = MIMEImage(img)
        fp.close()

        # Define the image's ID as referenced above
        msgImage.add_header('Content-ID', '<image1>')
        msgRoot.attach(msgImage)
        SendEmail(strFrom, strTo, msgRoot)

    def run(self):
        global Options
        counter = 0
        updated = False
        
        while True:
            counter += 1
            if not self._volt_sensor.isOnline():
                self.sendResult('Module %s has been disconnected' % self._volt_sensor.get_friendlyName(), 0)
                print("Thread had no found volt_sensor")
                return
            self._last_value = self._volt_sensor.get_currentValue()
            
            # Multiply the last value to account for voltage divider
            #self._last_value = round(self._last_value * 2)
            
            if not Options.verbose:
                print("%s: voltage is %2.1f c" % (self._volt_sensor.get_friendlyName(), self._last_value))
            
            # If we are recording
            if self._recording:
                
                # ONLY used for test mode
                if self._method_to_use == "test":
                    
                    if self._current_recording_stage == 1:
                        if abs(self._last_value) > .5:
                            self._module_recording_status = "Remove leads from module"
                        else:
                            self._module_recording_status = "Please Wait"
                            self._current_recording_stage = 2
                            
                    elif self._current_recording_stage == 2:
                        self._module_recording_status = "Apply leads to next module"
                        
                        if self._last_value > 6:
                            self._current_recording_stage = 3
                            self._recording_loop_helper = 1
                            self._module_recording_status = "Please Wait"
                            self._recording_start_time = datetime.datetime.today()
                            self.add_new_value(self._last_value, True, True)
                            
                    elif self._current_recording_stage == 3:
                        self._module_recording_status = "plotting 5 points.."
                        
                        if self._recording_loop_helper <= 5:
                            self._recording_loop_helper += 1
                            self.add_new_value(self._last_value)
                        
                        if self._recording_loop_helper > 5:
                            self._current_recording_stage = 4
                            self._module_recording_status = "Please Wait"
                            
                    elif self._current_recording_stage == 4:
                        self._module_recording_status = "Apply load"
                        
                        if abs(self._recording_data_y[-1] - self._last_value) > .2:
                            self._current_recording_stage = 5
                            
                            # Set recording start time to last recorded, so we continue where we left off
                            self._recording_start_time = datetime.datetime.today() + datetime.timedelta(seconds=-6.3)
                            print("last x value recorded: %s converted time: %s recording start time: %s" % (float(self._recording_data_label_x[-1]), datetime.timedelta(seconds=-6.3), self._recording_start_time))
                            
                            self._stopwatch = 0
                            self._module_recording_status = "Please Wait"
                            self.add_new_value(self._last_value, True, True)
    
                    elif self._current_recording_stage == 5:
                        self._module_recording_status = "Recording for configured time"
                        self.add_new_value(self._last_value)
                
                        # update timer
                        tmp = datetime.datetime.today() - self._recording_start_time
                        self._stopwatch = round(tmp.total_seconds(), 2)

                        if self._last_recorded >= self._recording_start_time + datetime.timedelta(minutes=self._target_value):
                            self._module_recording_status = "Recording complete. Please Wait"
                            self.add_new_value(self._last_value, True, True)
                            self._current_module += 1
                            self._current_recording_stage = 1
                            self._recording_loop_helper = 0
                            self._module_recording_status = "incrementing to next module"
                            self._target_reached = False
                            self._recording_data_x = []
                            self._recording_data_y = []
                            self._recording_data_label_x = []
                            self._recording_data_label_y = []
                            self._highest_value = 0
                            self._recording_start_time = datetime.datetime.today()
                            self._highest_value_last_recorded = datetime.datetime.today()
                            self._highest_value_start_time = datetime.datetime.today()
                            self._last_recorded = datetime.datetime.today()
                            self._graph_resolution = 1
                            self._stopwatch = 0

                # If target reached and NOT in test mode
                elif not self._target_reached and self.checkTargetValue(self._method_to_use, self._last_value, 
                self._target_value, self._last_recorded, self._recording_start_time, self._highest_value_last_recorded):
                    self.add_new_value(self._last_value, False, True)
                    msg = "###### target value of %s Minutes/Volts (method: %s) for %s has been reached ######" % (self._target_value, self._method_to_use, self.getName())
                    self._target_reached = True
                    self.plot_graph()
                    self.sendResult(msg, self._last_value)
                elif counter > 9:
                    self.add_new_value(self._last_value)
                    updated = True
            if updated:
                counter = 0
                updated = False
            YAPI.Sleep(1000)

def main():
    """ Main function, deals with arguments and launch program"""
    # Usual verifications and warnings
    global Options
    sys.stdout.write('Voltage Monitor v1.0 started\n')
    sys.stdout.write('using Yoctopuce version %s\n' % (YAPI.GetAPIVersion()))
    parser = OptionParser()
    parser.add_option("-v", "--verbose", action="store_true",
                      help="Write output information (not only errors).",
                      default=True)
    parser.add_option("-r", action="store", type="string", dest="hub",
                      default="127.0.0.1", help="Uses remote IP devices (or VirtalHub), instead of local USB"),
    parser.add_option("-p", "--port",
                      action="store", type="int", dest="http_port",
                      default="8080", help="The port used by the http server"),
    parser.add_option("--email",
                      action="store", type="string", dest="email",
                      default="", help="The default email where to send results"),
    parser.add_option("--smtp_host",
                      action="store", type="string", dest="mail_host",
                      default="smtp.gmail.com", help="SMTP server host name (smtp.gmail.com for gmail)"),
    parser.add_option("--smtp_port",
                      action="store", type="int", dest="mail_port",
                      default="587", help="SMTP server port number (587 for gmail)"),
    parser.add_option("--smtp_user",
                      action="store", type="string", dest="mail_user",
                      default="", help="Username for SMTP authentication (your gmail account)"),
    parser.add_option("--smtp_password",
                      action="store", type="string", dest="mail_pass",
                      default="", help="Password for SMTP authentication (your gmail password)"),
    parser.add_option("--root_dir",
                      action="store", type="string", dest="root_dir",
                      default=os.path.abspath(os.getcwd()), help="The directory where 'cherry.py' is in. Must have following slash! ie: '/home/pi/cherry/'"),
    (Options, args) = parser.parse_args()
    # THE program :-)
    if Options.verbose:
        print("SMPT Server info: %s:%d (%s:%s)" % (
            Options.mail_host, Options.mail_port, Options.mail_user, Options.mail_pass))
        # Setup the API to use local USB devices 
        
    print('Find public IP...')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("gmail.com", 80))
    MyIP = s.getsockname()[0]
    s.close()
    print(' Done (%s)' % MyIP)

    if Options.email != "":
        SendWelcomeEmail()
    else:
        print("No default email configured (skip email configuration test)")
        
    errmsg = YRefParam()
    print('List All Yoctopuce voltage Sensors.')
    # Setup the API to use local USB devices
    if YAPI.RegisterHub(Options.hub, errmsg) != YAPI.SUCCESS:
        sys.exit("init error" + str(errmsg))
    print('...')

    sensor = YVoltage.FirstVoltage()
    while sensor is not None:
        print('- %s' % sensor.get_friendlyName())
        trec = voltage_recorder(sensor, Options.email)
        trec.start()
        
        mainexists = os.path.isfile("public/images/plot.%s.png" % trec._volt_sensor.get_hardwareId())
        miniexists = os.path.isfile("public/images/miniplot.%s.png" % trec._volt_sensor.get_hardwareId())
        
        if mainexists and miniexists:
            print("main and mini plot file exists--skipping.")
        else:
            print("main or mini plot file does not exists--creating")
            trec.plot_graph() 
        
        AllSensors[sensor.get_hardwareId()] = trec
        sensor = sensor.nextVoltage()
    server = None

    if len(AllSensors) == 0:
        sys.exit("No Yocto-Volts detected")
    
    try:
        print('Starting HTTP server...')

        cherrypy.config.update({'server.socket_host': '0.0.0.0',
                        'server.socket_port': Options.http_port,
                        'log.error_file': '',
                        'log.access_file': '',
                        'log.screen': False,
                       })

        conf = {
            '/': {
                'tools.sessions.on': True,
                'tools.staticdir.root': Options.root_dir
            },
            '/static': {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': 'public'
            }
        }
        
        cherrypy.quickstart(MainPage(), '/', conf)
        
    except KeyboardInterrupt:
        print('^C received, shutting down server')
        
if __name__ == '__main__':
    main()