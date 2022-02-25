#!/usr/bin/python3

import configparser
import untangle
import requests
import json
import pprint

pp = pprint.PrettyPrinter(indent=4)

config = configparser.ConfigParser(interpolation=None)
config.read('config/config.ini')

memberships = {}
stream_mapping = {}

credentials = {'username':'automation', 'password': 'E82yEruavpYdUsXhVdwL'}

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
	if "|" in groupName:
		stream_id = groupName.split('|')[0].strip()
		stream_mapping[stream_id] = group['id']

#gradebook = untangle.parse(config['data']['stream_uri'])
gradebook = untangle.parse('testdata.xml')

memberships = {}

for result in gradebook.results.result:
	if result.score == '100 %':
		if result.assignment.cdata in stream_mapping:
			if not result.student.cdata in memberships:
				memberships[result.student.cdata] = []

			memberships[result.student.cdata].append(int(stream_mapping[result.assignment.cdata]))

getAllUsersURI = config['data']['booked_uri'] + "/Users/"
r = requests.get(getAllUsersURI, headers=headers)

for user in r.json()['users']:
	if user['userName'] in memberships:
		updateUserURI = config['data']['booked_uri'] + "/Users/" + user['id']
		user['groups'] = memberships[user['userName']]
		r = requests.post(updateUserURI, data=json.dumps(user), headers=headers)

## Sign out of the session
signoutURI = config['data']['booked_uri'] + "/Authentication/SignOut"
signoutData = {'userId':auth['userId'],"sessionToken":auth['sessionToken']}
r = requests.post(signoutURI, data=json.dumps(signoutData))
