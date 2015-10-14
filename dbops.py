#! /usr/bin/python3.4

import datetime
import pymongo
import validations

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
            user = getuser(a)
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

        def insertUser(self, a, m, n=None, setExpiry = False):
            user = getuser(a)
            if user:
                return True

            if setExpiry:
                utc_timestamp = datetime.datetime.utcnow()
                if n:
                   self.getdb().users.insert( {'mapped': m, 'actual': a, 'name' : n, 'Expiry_date' : utc_timestamp} )
                else:
                   self.getdb().users.insert( { 'mapped': m, 'actual': a, 'Expiry_date': utc_timestamp } )
            else:
                if n:
                   self.getdb().users.insert( {'mapped': m, 'actual': a, 'name' : n} )
                else:
                   self.getdb().users.insert( { 'mapped': m, 'actual': a } )

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
            mailthread =self.getdb().threadMapper.find_one( { 'threadId' : msgId } )
            return mailthread

        def insertThread(self, msgId, references =None):
            timestamp = datetime.datetime.now()
            utc_timestamp = datetime.datetime.utcnow()
            if references is None:
                self.getdb().threadMapper.insert( { 'threadId' : msgId , "date": timestamp, "Expiry_date" : utc_timestamp} )
            else:
                self.getdb().threadMapper.insert( { 'threadId' : msgId, 'references' : references,
                                        "date": timestamp, "Expiry_date" : utc_timestamp} )

        def findDeregistedUser(self, from_email):
            duser = self.getdb().deregisteredUsers.find_one ( { 'actual' : from_email } )
            return duser

        def updateExpAndInsertDeregUser(self, user):
            utc_timestamp = datetime.datetime.utcnow()
            self.getdb().users.update({"actual": user['actual']},
                                      {"$set": {'Expiry_date': utc_timestamp}})

            self.getdb().deregisteredUsers.insert( user )
            return

        def getBackUpdb():
            return self.backupdb

        def getLidb():
            return self.lidb


