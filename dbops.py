#! /usr/bin/python3.4

import datetime
import json

import pymongo

import validations

def convertDictToJson(data):
    json_data = json.dumps(data)
    return json_data

class MongoORM:
    def __init__(self):
        try:
            self.conn = pymongo.MongoClient()
            print ("Connected successfully!!!")
        except pymongo.errors.ConnectionFailure as e:
            print ("Could not connect to MongoDB: %s" % e )

        self.valids = validations.Validations()

        self.db = self.conn.inbounddb

        self.backupdb = self.conn.inbounddb.mailBackup

        self.lidb = self.conn.inbounddb.liMailBackUp

        self.mccdb = self.conn.inbounddb.mccdb

        self.backupdb.ensure_index("Expiry_date", expireAfterSeconds=0)

        #Set expiry after 24 hours
        self.db.threadMapper.ensure_index("Expiry_date", expireAfterSeconds=24*60*60)

        #TTL for invites users .. expiry after 5 mins
        self.db.users.ensure_index("Expiry_date", expireAfterSeconds=24*60*60)

        #expire after 30days from now
        self.db.invitesRecipients.ensure_index("Expiry_date", expireAfterSeconds=0)

    def getdb(self):
        return self.db

    def getactual(self, a):
        user = self.getuser(a)
        if not user:
            return None
        return user['actual']

    def getuser(self, a):
        if self.valids.isourdomain(a):
            user = self.getdb().users.find_one({'mapped': a})
        else:
            user = self.getdb().users.find_one({'actual': a})
        return user

    def isknowndomain(self, a):
        if self.valids.isourdomain(a):
            return True
        domain = self.valids.getdomain(a)
        known = self.getdb().domains.find_one({'domain': domain })
        if not known:
            return False
        return True

    def insertUser(self, a, m, n=None, setExpiry = False, phoneValidated=False):
        user = self.getuser(a)
        if user:
            return True

        data = dict()
        data['actual'] = a
        data['mapped'] = m

        if n:
            data['name'] = n

        if setExpiry: 
            utc_timestamp = datetime.datetime.utcnow()
            data['setExpiry'] = utc_timestamp

        phValid = 'False'
        if phoneValidated:
            phValid = 'True'
        
        data['phone_verified'] = phValid
        json_data = convertDictToJson(data)

        self.getdb().users.insert( json_data )

        del data
        del json_data

        return True

    def getmapped(self, a):
        user = self.getuser(a)
        if not user:
            return None
        return user['mapped']

    def findInviteUsers(self, mailid):
        user = self.getdb().invitesRecipients.find_one( { 'email' : mailid } )
        return user

    def insertIntoInviteRecipients(self, mailid):
        utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        self.getdb().invitesRecipients.insert( { 'email' : mailid, 'Expiry_date' : utc_timestamp } )
        return

    def findThread(self, msgId):
        mailthread = self.getdb().threadMapper.find_one( { 'threadId' : msgId } )
        return mailthread

    def insertThread(self, msgId, references =None):
        timestamp = datetime.datetime.now()
        utc_timestamp = datetime.datetime.utcnow()
        
        data = dict()
        data['threadId'] =  msgId
        data['date'] =  timestamp
        data['Expiry_date'] = utc_timestamp

        if references:
            data['references'] = references

        json_data = convertDictToJson(data)

        self.getdb().threadMapper.insert( json_data)
        del data
        del json_data

        return

    def findDeregistedUser(self, from_email):
        duser = self.getdb().deregisteredUsers.find_one ( { 'actual' : from_email } )
        return duser

    def updateExpAndInsertDeregUser(self, user):
        utc_timestamp = datetime.datetime.utcnow()
        self.getdb().users.update({"actual": user['actual']},
                                  {"$set": {'Expiry_date': utc_timestamp}})

        self.getdb().deregisteredUsers.insert( user )
        return

    def getBackUpdb(self):
        return self.backupdb

    def getLidb(self):
        return self.lidb

    def removeUser(self, user):
        self.getdb().users.remove( user )
        return

    def updatePluscode(self, actual, pluscode):
        self.getdb().users.update ( {'actual' : actual }, {'$set' : {'pluscode': pluscode}})
        return

    def updateMapped(self, actual, mapped):
        self.getdb().users.update ( {'actual' : actual }, {'$set' : {'mapped': mapped}})
        return

    def dumpmail(self, message):
        jsondata = json.loads(message)
        utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        self.getBackUpdb().insert( {'from':jsondata['fa'], 'Expiry_date' : utc_timestamp, 'inboundJson':message } )
        return

    def lidump(self, itemlist, data):
        self.getLidb().insert( { 'tagged':itemlist[0], 'inboundJson':data })
        return

    def getmccdb(self):
        return self.mccdb

    def getMCC(self, mcc):
        return self.getmccdb().find( { mcc :  { '$exists' : 'true' } } )