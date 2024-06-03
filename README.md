# midi2vjoy-again
Translates Midi input to Vjoy virtual joystick

Based on c0redumb's [midi2vjoy](https://github.com/c0redumb/midi2vjoy).

Takes in midi from a midi device, and based on the configuration controls a Vjoy device with that midi data.

In the simplest case, you can press a Vjoy button with a midi note and set a Vjoy axis with CC input.
You can also control a button state with CC, set a Vjoy axis to a specific value with a note, toggle a Vjoy button with a note and make a Vjoy button press of a defined length with a note. You can setup these things with a .conf file, and the example demo.conf explains the settings.

Getting midi2vjoy-again to work you need to have python installed, and the pygame python module installed. You can check the the installing procedure from the original [midi2vjoy](https://github.com/c0redumb/midi2vjoy). If you can get the original one to work, this one should work too.

Using midi2vjoy-again is much the same as with the original midi2vjoy. Start by 'midi2vjoy-again -t' (or 'python midi2vjoy-again.py -t' works in Powershell) to start in test mode. You should be able to select a midi device, once that is done, start pressing notes and adjusting CC controls on your midi device, and you should be seeing midi data coming in. You can take note of note and cc numbers and the channel so you can use them later.

Then you write or edit the conf file. The demo.conf has examples and comments. Make sure Vjoy is running, and start with 'python .\midi2vjoy-again.py -m 1 -c yourConfFile.conf' and you should be good to go. With -m option you select the correct midi device, the same number you selected in test mode.
