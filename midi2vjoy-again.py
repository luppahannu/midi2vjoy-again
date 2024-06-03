#  modified from midi2vjoy.py  
#  Copyright 2017  <c0redumb>
#  
# midi2vjoy-again.py 
# luppahannu 2024

import sys, os, time, traceback
import ctypes
from optparse import OptionParser
import pygame.midi
import winreg
from enum import Enum
import time

# Constants
# Axis mapping
axis = {'X': 0x30, 'Y': 0x31, 'Z': 0x32, 'RX': 0x33, 'RY': 0x34, 'RZ': 0x35,
		'SL0': 0x36, 'SL1': 0x37, 'WHL': 0x38, 'POV': 0x39}

class E(Enum):
	note = -2
	noteOff = 0b10000000
	noteOn = 0b10010000
	cc = 0b10110000
	progChange = 0b11000000
	pitchBend = 0b11100000
	toggle = -1
	

# Slider or Pitchbend keys(m_types)
# sliders = {176, 224}

# Buttons with different On/Off keys(m_types)
#144 = 1001 0000, 128 = 1000 0000 (144:n note off), 153 = 1001 1001, 137 = 1000 1001
# btns = {144, 128, 153, 137}

# If you want somthing with an m_type of 176 or 244 to behave like a btn 
# put the m_control value here
#sliderOverride = {}

	
# Globals
options = None

""" def midiTypeAndChannelToStatus(type, channel):
    status = channel - 1
    if type == E.noteOn:
        status += 144
    elif type == E.cc:
        status += 176	
    return status

def midiStatusToTypeAndChannel(status):
	type = status & 0b11110000
	channel = status & 0b00001111
	return (type, channel)
 """	
	

def midi_test():
	n = pygame.midi.get_count()

	# List all the devices and make a choice
	print('Input MIDI devices:')
	for i in range(n):
		info = pygame.midi.get_device_info(i)
		if info[2]:
			print(i, info[1].decode())
	d = int(input('Select MIDI device to test: '))
	
	# Open the device for testing
	try:
		print('Opening MIDI device:', d)
		m = pygame.midi.Input(d)
		print('Device opened for testing. Use ctrl-c to quit.')
		while True:
			while m.poll():
				midiInput=m.read(1)
				print(midiInput, end = " ")
				midiInputStatus = midiInput[0][0][0]
				midiInputData1 = midiInput[0][0][1]
				midiInputData2 = midiInput[0][0][2]
				type = midiInputStatus & 0b11110000
				channel = (midiInputStatus & 0b00001111) + 1
				if type == E.noteOn.value:
					print("NoteOn, channel", channel, ", note", midiInputData1, ", velocity", midiInputData2, end = "")
				elif type == E.noteOff.value:
					print("NoteOff, channel", channel , ", note", midiInputData1, end="")
				elif type == E.cc.value:
					print("CC, channel", channel, ", controller number", midiInputData1, ", value", midiInputData2, end="")
				elif type == E.pitchBend.value:
					pbVal = (midiInputData2<<7) + midiInputData1
					print("Pitch bend, channel", channel, ", value", pbVal, end="")
				print("")
				#print("type", type, ", channel", channel)
			time.sleep(0.1)
	except:
		m.close()
		
def read_conf(conf_file):
	'''Read the configuration file'''
	table = []
	triggerCodes = []
	vids = []
	with open(conf_file, 'r') as f:
		added = 0
		for l in f:
			if len(l.strip()) == 0 or l[0] == '#':
				continue
			fs = l.split()
			
			try:
				#into this dict is written the stuff read and interpreted from the conf file. Then the dict
				#is appended into table
				#into button is written the current state of the button, if a button is being controlled.
				#Used mostly for the toggling
				dict = {
					"type": fs[0], #is it a note or CC
					"channel": int(fs[1]),
					"noteOrCC": -1, #note number or CC number
					"vJoyID": int(fs[3]),
					"vJoyControl": fs[4],
					"extra": "none",
					"button": False, #current state of the button, used mostly for toggling
					"timePressed": 0.0,	#time in unixtime when button was pressed
					"timeToPress": 0.0	#for how many seconds the button should be pressed
				}

				#triggerCodes hold two bytes, essentially the first two bytes of MIDI noteOn or cc message
				#Its a way for putting message type, channel and note/cc type into one number
				triggerCode = 0
				if fs[0] == "cc":
					triggerCode += E.cc.value<<8
					#cc number
					triggerCode += int(fs[2])
					dict["noteOrCC"] = int(fs[2])
				elif fs[0] == "note":
					#triggerCode has noteOn values, when comparing to incoming notes, noteOff messages are
					#converted to noteOn messages
					triggerCode += E.noteOn.value<<8
					#note number
					triggerCode += int(fs[2])
					dict["noteOrCC"] = int(fs[2])
				elif fs[0] == "pb":
					triggerCode += E.pitchBend.value<<8

				#handling of possible extra value
				if len(fs) > 5:
					extra = fs[5]
					if fs[0] == "cc":
						n = int(extra)
						#print("number in extra field", n)
						dict["extra"] = extra
						#if (n < 128) and (n > -128):
						#	dict["extra"] = fs[5]
					elif fs[0] == "note":
						if extra == "toggle":
							dict["extra"] = E.toggle.value
						elif extra.isnumeric():
							if fs[4].isnumeric(): 
								#VjoyControl and extra can't both have numeric values with a note
								raise Exception("with a note input, button output and numerical extra field are not valid") 
							else:
								dict["extra"] = int(extra)
						elif extra[len(extra) - 1] == "s":
							n=extra[0:(len(extra) - 1)]
							#print("time to keep button pressed", n)
							dict["timeToPress"] = float(n)

					
				#MIDI channel
				triggerCode += (int(fs[1]) - 1)<<8
				
				triggerCodes.append(triggerCode)
				table.append(dict)
				added+=1
				if options.verbose:
					print("triggerCode", bin(triggerCode))
				vid = int(fs[3])
				if not vid in vids:
					vids.append(vid)
			except:
				print('Bad line in conf file, ', l)
		#print("added", added, "values")
		#print("len(triggerCodes)", len(triggerCodes))
	return (table, vids, triggerCodes)

def handleMidiInput(midiInput, triggerCodes, table, vjoy, runningButtonTimers):
	#print(midiInput)
	#key = tuple(midiInput[0][0][0:2])
	#reading = midiInput[0][0][2]
	midiInputStatus = midiInput[0][0][0]
	midiInputData1 = midiInput[0][0][1]
	midiInputData2 = midiInput[0][0][2]
	print("midiInputStatus", midiInputStatus, ", midiInputData1", midiInputData1, ", midiInputData2", midiInputData2)
	#print("key[0]", key[0], ", key[1]", key[1], ", reading", reading)
	#type = key[0] & 0b11110000
	type = midiInputStatus & 0b11110000
	#channel = key[0] & 0b00001111
	trig = (midiInputStatus<<8)
	#in pitch bend, data1 is part of the bending value, can't use it for trigger comparisons.
	#with NoteOn and NoteOff data1 is the note number, with CC it's the CC number 
	if type != E.pitchBend.value:
		trig += midiInputData1
	if type == E.noteOff.value:
		#print("Note off")
		#triggerCodes table has comparable values for NoteOn events. Just for comparison,
		#lets change the incoming noteOff to look like a noteOn
		trig += 0b0001000000000000
	#searching if the incoming trigger is found in triggerCodes. If an index (i) is found, the same 
	#index number corresponds to table 
	i=0
	try:
		i = triggerCodes.index(trig)
	except:
		return
	
	if options.verbose:
		print("found triggerCode", bin(triggerCodes[i]), ", i =", i)
	#SetBtn(BOOL Value, UINT rID, UCHAR nBtn);
	noteToggle = False
	if table[i]["extra"] == E.toggle.value:
		noteToggle = True
	setAxis = True
	if table[i]["vJoyControl"].isnumeric():
		setAxis = False
	

	if type == E.noteOn.value:
		if not noteToggle:
			if setAxis:
				axisValue = 16384
				if table[i]["extra"] != "none":
					axisValue = table[i]["extra"]
				vjoy.SetAxis(axisValue, table[i]["vJoyID"], axis[table[i]["vJoyControl"]])
				print("setting axis", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
			else: #ordinary noteOn
				print("setting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
				vjoy.SetBtn(True, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
				table[i]["button"] == True
				if table[i]["timeToPress"] != 0.0:
					table[i]["timePressed"] = time.time()
					if not i in runningButtonTimers:
						runningButtonTimers.append(i)
		else: #noteToggle True
			if table[i]["button"] == False:
				vjoy.SetBtn(True, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
				table[i]["button"] = True
				print("setting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
			else:
				vjoy.SetBtn(False, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
				print("resetting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
				table[i]["button"] = False

	elif (type == E.noteOff.value) and not noteToggle and not setAxis:
		if not i in runningButtonTimers:
			vjoy.SetBtn(False, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
			print("resetting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
			table[i]["button"] = False



	elif type == E.cc.value:
		#if thing to be controlled is just a number, it's a button, on at certain cc values, off at others 
		if not setAxis:
			comparisonNumber = 64
			if table[i]["extra"] != "none":
				comparisonNumber = int(table[i]["extra"])
			#print("comparisonNumber", comparisonNumber)
			if comparisonNumber > -1: 
				if int(midiInputData2) < comparisonNumber:
					vjoy.SetBtn(False, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
					table[i]["button"] = False
					print("resetting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
				else:
					vjoy.SetBtn(True, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
					table[i]["button"] = True
					print("setting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
			else: #extra number is negative, the button pressing action is reversed
				if int(midiInputData2) < abs(comparisonNumber):
					vjoy.SetBtn(True, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
					table[i]["button"] = True
					print("setting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
				else:
					vjoy.SetBtn(False, table[i]["vJoyID"], int(table[i]["vJoyControl"]) )
					table[i]["button"] = False
					print("resetting button", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
		#SetAxis(LONG Value, UINT rID, UINT Axis);		// Write Value to a given axis defined in the specified VDJ
		else:
			vjoy.SetAxis(((midiInputData2 + 1)<<8), table[i]["vJoyID"], axis[table[i]["vJoyControl"]])
			print("setting axis", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )


	elif type == E.pitchBend.value:
		#print(bin(midiInputData2), bin(midiInputData1))
		pbVal = (midiInputData2<<8) + (midiInputData1<<1) + 1
		print("pitch bend value", pbVal)
		vjoy.SetAxis(pbVal, table[i]["vJoyID"], axis[table[i]["vJoyControl"]])
		print("setting axis", table[i]["vJoyControl"], "on vJoy device", table[i]["vJoyID"] )
		

def joystick_run():
	# Process the configuration file
	if options.conf == None:
		print('Must specify a configuration file')
		return
	try:
		if options.verbose:
			print('Opening configuration file:', options.conf)
		(table, vids, triggerCodes) = read_conf(options.conf)
		if options.verbose:
			for t in table:
				print(t)
		#print(vids)
	except:
		print('Error processing the configuration file:', options.conf)
		return
		
	# Getting the MIDI device ready
	if options.midi == None:
		print('Must specify a MIDI interface to use')
		return
	try:
		if options.verbose:
			print('Opening MIDI device:', options.midi)
		midi = pygame.midi.Input(options.midi)
	except:
		print('Error opting MIDI device:', options.midi)
		return
		
	# Load vJoysticks
	try:
		# Load the vJoy library
		# Load the registry to find out the install location
		vjoyregkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{8E31F76F-74C3-47F1-9550-E041EEDC5FBB}_is1')
		installpath = winreg.QueryValueEx(vjoyregkey, 'InstallLocation')
		winreg.CloseKey(vjoyregkey)
		#print(installpath[0])
		dll_file = os.path.join(installpath[0], 'x64', 'vJoyInterface.dll')
		vjoy = ctypes.WinDLL(dll_file)
		#print(vjoy.GetvJoyVersion())
		
		# Getting ready
		for vid in vids:
			if options.verbose:
				print('Acquiring vJoystick:', vid)
			assert(vjoy.AcquireVJD(vid) == 1)
			assert(vjoy.GetVJDStatus(vid) == 0)
			vjoy.ResetVJD(vid)
	except:
		#traceback.print_exc()
		print('Error initializing virtual joysticks')
		return
	
	runningButtonTimers = []
	try:
		if options.verbose:
			print('Ready. Use ctrl-c to quit.')
		while True:
			while midi.poll():
				midiInput = midi.read(1)
				handleMidiInput(midiInput, triggerCodes, table, vjoy, runningButtonTimers)

			time.sleep(0.1)
			if len(runningButtonTimers) > 0:
				#print('timers in runningButtonTimers')
				timeNow = time.time()
				for timerIndex in runningButtonTimers:
					if (timeNow - table[timerIndex]["timePressed"]) > table[timerIndex]["timeToPress"]:
						print('timeout for button', table[timerIndex]["vJoyControl"])
						runningButtonTimers.remove(timerIndex)
						vjoy.SetBtn(False, table[timerIndex]["vJoyID"], int(table[timerIndex]["vJoyControl"]) )
						table[timerIndex]["button"] = False

	except:
		#traceback.print_exc()
		pass
		
	# Relinquish vJoysticks
	for vid in vids:
		if options.verbose:
			print('Relinquishing vJoystick:', vid)
		vjoy.RelinquishVJD(vid)
	
	# Close MIDI device
	if options.verbose:
		print('Closing MIDI device')
	midi.close()
		
def main():
	# parse arguments
	parser = OptionParser()
	parser.add_option("-t", "--test", dest="runtest", action="store_true",
					  help="To test the midi inputs")
	parser.add_option("-m", "--midi", dest="midi", action="store", type="int",
					  help="File holding the list of file to be checked")
	parser.add_option("-c", "--conf", dest="conf", action="store",
					  help="Configuration file for the translation")
	parser.add_option("-v", "--verbose",
						  action="store_true", dest="verbose")
	parser.add_option("-q", "--quiet",
						  action="store_false", dest="verbose")
	global options
	(options, args) = parser.parse_args()
	
	pygame.midi.init()
	
	if options.runtest:
		midi_test()
	else:
		joystick_run()
	
	pygame.midi.quit()

if __name__ == '__main__':
	main()
