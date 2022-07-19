#!/usr/bin/python3

## Synchronizes LibreBooking Groups using Moodle Assessment Results

import configparser
import untangle
import requests
import json
import time
from datetime import datetime

import pprint

pp = pprint.PrettyPrinter(indent=4)

config = configparser.ConfigParser(interpolation=None)
config.read('config/config.ini')
interval = int(config['schedule']['interval'])
print("LibreBooking - Moodle Synchroniser Started")
print("Polling Interval set to: " + str(interval) + " seconds")
print("All enrolled users will be added to: " + str(config['data']['all_enrolled_group']))

while True:
	memberships = {}
	stream_mapping = {}

	credentials = {'username':config['booked_credentials']['username'], 'password': config['booked_credentials']['password']}

	authURI = config['data']['booked_uri'] + "/Authentication/Authenticate"
	r = requests.post(authURI, data=json.dumps(credentials))
	auth = r.json()

	headers = {'X-Booked-SessionToken':auth['sessionToken'], 'X-Booked-UserId':auth['userId']}

	groupsURI = config['data']['booked_uri'] + "/Groups"
	r = requests.get(groupsURI, headers=headers)

	lbGroups = r.json()

	# Parse the group names to find the mapping for stream Common Module IDs
	for group in lbGroups['groups']:
		groupName = group['name']
		if groupName == config['data']['all_enrolled_group']:
			stream_mapping['enrolled'] = group['id']
		if "|" in groupName:
			stream_id = groupName.split('|')[0].strip()
			stream_mapping[stream_id] = group['id']

	gradebook = untangle.parse(config['data']['stream_uri'])

	memberships = {}

	for result in gradebook.results.result:
		if not result.student.cdata in memberships:
			memberships[result.student.cdata] = [stream_mapping['enrolled']]
		if result.score == '100 %':
			if result.assignment.cdata in stream_mapping:
				memberships[result.student.cdata].append(int(stream_mapping[result.assignment.cdata]))

	getAllUsersURI = config['data']['booked_uri'] + "/Users/"
	r = requests.get(getAllUsersURI, headers=headers)

	for user in r.json()['users']:
		if user['userName'] in memberships:
			getUserURI = config['data']['booked_uri'] + "/Users/" + user['id']
			r = requests.get(getUserURI, headers=headers)
			userDetails = r.json()
			groups = [int(d['id']) for d in userDetails['groups']]
			groups.sort()
			memberships[user['userName']].sort()
			if not groups == memberships[user['userName']]:
				updateUserURI = config['data']['booked_uri'] + "/Users/" + user['id']
				user['groups'] = memberships[user['userName']]
				r = requests.post(updateUserURI, data=json.dumps(user), headers=headers)
				groups_strings = [str(gid) for gid in user['groups']]
				print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\tUpdated permissions for " + user['userName'] + " (GIDs: " + ", ".join(groups_strings) + ")")

	## Sign out of the session
	signoutURI = config['data']['booked_uri'] + "/Authentication/SignOut"
	signoutData = {'userId':auth['userId'],"sessionToken":auth['sessionToken']}
	r = requests.post(signoutURI, data=json.dumps(signoutData))

	time.sleep(interval)
