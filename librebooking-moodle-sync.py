#!/usr/bin/python3

import schedule
import time
import configparser
import untangle
import requests
import json
from datetime import datetime
import os

import pprint
pp = pprint.PrettyPrinter(indent=4)

config = configparser.ConfigParser(interpolation=None)
config.read(os.path.join(os.path.dirname(__file__),'config/config.ini'))

gradebook_interval = int(config['schedule']['gradebook_interval'])
sync_interval = int(config['schedule']['librebooking_interval'])
full_resync = int(config['schedule']['full_resync'])

cmid_mapping = {}	# Maps common-module IDs to LibreBooking Groups
memberships = {}	# Holds group membership data for all enrolled users

syncedUsers = 0

def update_cmid_mapping():
	headers = authenticate()
	groupsURI = config['data']['librebooking_uri'] + "/Groups"
	r = requests.get(groupsURI, headers=headers)

	lbGroups = r.json()

	# Parse the group names to find the mapping for Moodle Common Module IDs or Special Keywords
	for group in lbGroups['groups']:
		groupName = group['name']
		if "|" in groupName:
			cmid = groupName.split('|')[0].strip().lower()
			cmid_mapping[cmid] = int(group['id'])
	signout(headers)

def update_memberships():
	try:
		gradebook = untangle.parse(config['data']['gradebook_uri'])
	except:
		print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\tError connecting to Moodle")
		return

	changedCount = 0

	for result in gradebook.results.result:
		if not result.student.cdata in memberships:
			memberships[result.student.cdata] = { 'groups':[cmid_mapping['enrolled']] }
			memberships[result.student.cdata]['changed'] = True
		if result.score == '100 %':
			if result.assignment.cdata in cmid_mapping:
				if int(cmid_mapping[result.assignment.cdata]) not in memberships[result.student.cdata]['groups']:
					memberships[result.student.cdata]['groups'].append(int(cmid_mapping[result.assignment.cdata]))
					memberships[result.student.cdata]['changed'] = True

def sync_memberships():
	headers = authenticate()
	getAllUsersURI = config['data']['librebooking_uri'] + "/Users/"
	r = requests.get(getAllUsersURI, headers=headers)

	for user in r.json()['users']:					# Loop through the list of users from LibreBooking
		if user['userName'] in memberships:			# If they're in the memberships list
			if memberships[user['userName']]['changed']:	# And the record has been updated since last sync
				memberships[user['userName']]['changed'] = False
				getUserURI = config['data']['librebooking_uri'] + "/Users/" + user['id']
				r = requests.get(getUserURI, headers=headers)
				userDetails = r.json()
				groups = [int(d['id']) for d in userDetails['groups']]
				groups.sort()
				memberships[user['userName']]['groups'].sort()
				if not groups == memberships[user['userName']]['groups']:
					updateUserURI = config['data']['librebooking_uri'] + "/Users/" + user['id']
					user['groups'] = memberships[user['userName']]['groups']
					r = requests.post(updateUserURI, data=json.dumps(user), headers=headers)
					groups_strings = [str(gid) for gid in user['groups']]
					print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\tUpdated permissions for " + user['userName'] + " (GIDs: " + ", ".join(groups_strings) + ")")
	signout(headers)

def stale_all_memberships():
	for user in memberships:
		memberships[user]['changed'] = True

## Removes unenrolled users from managed groups
def cleanup_groups():
	headers = authenticate()
	getAllUsersURI = config['data']['librebooking_uri'] + "/Users/"
	r = requests.get(getAllUsersURI, headers=headers)

	for user in r.json()['users']:
		if user['userName'] not in memberships:	# If a user isn't in the 'memberships' list, they aren't enrolled and so shouldn't be in any managed groups.
			getUserURI = config['data']['librebooking_uri'] + "/Users/" + user['id']
			r = requests.get(getUserURI, headers=headers)
			userDetails = r.json()
			groups = [int(d['id']) for d in userDetails['groups']]
			for cmid in cmid_mapping:
				if cmid_mapping[cmid] in groups:
					updateUserURI = config['data']['librebooking_uri'] + "/Users/" + user['id']
					groups.remove(cmid_mapping[cmid])
					user['groups'] = groups
					r = requests.post(updateUserURI, data=json.dumps(user), headers=headers)
					print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\t" + user['userName'] + " is no longer enrolled, removed from managed groups.")
	signout(headers)

## LibreBooking Authentication Routines
def authenticate():
	credentials = {'username':config['librebooking_credentials']['username'], 'password': config['librebooking_credentials']['password']}
	authURI = config['data']['librebooking_uri'] + "/Authentication/Authenticate"
	r = requests.post(authURI, data=json.dumps(credentials))
	auth = r.json()
	headers = {'X-Booked-SessionToken':auth['sessionToken'], 'X-Booked-UserId':auth['userId']}
	return(headers)

def signout(headers):
	signoutURI = config['data']['librebooking_uri'] + "/Authentication/SignOut"
	signoutData = {'userId':headers['X-Booked-UserId'],"sessionToken":headers['X-Booked-SessionToken']}
	r = requests.post(signoutURI, data=json.dumps(signoutData))

##
## Scheduling
##

schedule.every().day.at("23:30").do(update_cmid_mapping)
schedule.every().day.at("23:35").do(cleanup_groups)
schedule.every(gradebook_interval).minutes.do(update_memberships)
schedule.every(sync_interval).minutes.do(sync_memberships)
schedule.every(full_resync).hours.do(stale_all_memberships)

print("Moodle -> Librebooking Sync Starting")
print("Gradebook pull interval:",gradebook_interval,"minutes")
print("LibreBooking sync interval:",sync_interval,"minutes")

# Initial population of the CMID map
print("Initial pull for CMID map from LibreBooking: ", end='')
update_cmid_mapping()
print(len(cmid_mapping),"group mappings retrieved")

# Initial population of memberships
print("Initial pull of Moodle gradebook for memberships mapping: ", end='')
update_memberships()
print(len(memberships), "users retrieved")

##
## Main Loop
##

while True:
    schedule.run_pending()
    time.sleep(1)
