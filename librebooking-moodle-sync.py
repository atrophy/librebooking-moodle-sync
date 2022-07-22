#!/usr/bin/python3

import schedule
import time
import configparser
import untangle
import requests
import json
from datetime import datetime

import pprint
pp = pprint.PrettyPrinter(indent=4)

config = configparser.ConfigParser(interpolation=None)
config.read('config/config.ini')

gradebook_interval = int(config['schedule']['gradebook_interval'])

cmid_mapping = {}	# Maps common-module IDs to LibreBooking Groups
memberships = {}	# Holds group membership data for all enrolled users


def update_cmid_mapping():
	headers = authenticate()
	groupsURI = config['data']['booked_uri'] + "/Groups"
	r = requests.get(groupsURI, headers=headers)

	lbGroups = r.json()

	# Parse the group names to find the mapping for stream Common Module IDs or Special Keywords
	for group in lbGroups['groups']:
		groupName = group['name']
		if "|" in groupName:
			cmid = groupName.split('|')[0].strip()
			cmid_mapping[cmid] = int(group['id'])
	signout(headers)

def update_memberships():
	try:
		gradebook = untangle.parse(config['data']['stream_uri'])
	except:
		print("Error connecting to Moodle")
		return

	for result in gradebook.results.result:
		if not result.student.cdata in memberships:
			memberships[result.student.cdata] = [cmid_mapping['enrolled']]
		if result.score == '100 %':
			if result.assignment.cdata in cmid_mapping:
				memberships[result.student.cdata].append(int(cmid_mapping[result.assignment.cdata]))

def sync_memberships():
	headers = authenticate()
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
	signout(headers)

## LibreBooking Authentication Routines
def authenticate():
	credentials = {'username':config['booked_credentials']['username'], 'password': config['booked_credentials']['password']}
	authURI = config['data']['booked_uri'] + "/Authentication/Authenticate"
	r = requests.post(authURI, data=json.dumps(credentials))
	auth = r.json()
	headers = {'X-Booked-SessionToken':auth['sessionToken'], 'X-Booked-UserId':auth['userId']}
	return(headers)

def signout(headers):
	signoutURI = config['data']['booked_uri'] + "/Authentication/SignOut"
	signoutData = {'userId':headers['X-Booked-UserId'],"sessionToken":headers['X-Booked-SessionToken']}
	r = requests.post(signoutURI, data=json.dumps(signoutData))

##
## Scheduling
##

schedule.every().day.at("23:30").do(update_cmid_mapping)
schedule.every(gradebook_interval).minutes.do(update_memberships)

print("Moodle -> Librebooking Sync Starting")
print("Gradebook pull interval:",gradebook_interval,"minutes")

# Initial population of the CMID map
print("Initial pull for CMID map from LibreBooking: ", end='')
update_cmid_mapping()
pp.pprint(cmid_mapping)

# Initial population of memberships
print("Initial pull for memberships list from Moodle: ", end='')
update_memberships()
print(len(memberships), "users retrieved")


##
## Main Loop
##

while True:
    schedule.run_pending()
    time.sleep(1)
