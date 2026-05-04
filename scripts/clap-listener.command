#!/bin/bash
# Jarvis clap listener wrapper. Launched via Terminal so it inherits Terminal's mic permission.
# Output is mirrored to clap-trigger.log for monitoring.
cd "/Users/ki_lab_kitchen_narketing/Desktop/AI-Projects/_New-Project/jarvis-voice-assistant"
exec /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -u scripts/clap-trigger.py 2>&1 | tee clap-trigger.log
