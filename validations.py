#! /usr/bin/python3.4

import uuid
import phonenumbers

OUR_DOMAIN = 'readdress.io'

#allowedcountries = [91,61,1]

class PhoneValidations:
    def __init__(self, phnumber):
        self.number = 0
        self.number = phnumber
        self.numberdata = None
        self.error = None
        self.valid = True

    def validate(self):
        try:
            self.numberdata = phonenumbers.parse(self.number,None)
        except phonenumbers.phonenumberutil.NumberParseException as e:
            self.error = e
            self.valid = False

        return self.valid

    def get_result(self):
        return self.error

    def is_number_valid(self):
        if not phonenumbers.is_possible_number(self.numberdata) or not phonenumbers.is_valid_number(self.numberdata):
            self.valid = False
            return self.valid

    def is_allowed_MCC(self, dbhandle=None):
        dballoc = False
        if dbhandle is None:
            import dbops
            db = dbops.MongoORM()
            dbhandle = db

        if not dbhandle.getMCC(self.numberdata.country_code):
            self.valid = False

        if dballoc:
            del db
            del dbhandle 

        return self.valid


class Validations:
    def getdomain(self, a):
        return a.split('@')[-1]

    def getuserid(self, a):
        return a.split('@')[0]

    def isourdomain(self, a):
        return self.getdomain(a) == OUR_DOMAIN

    def valid_uuid4(self, a):
        userid = self.getuserid(a)
        try:
            val = uuid.UUID(userid, version=4)
        except ValueError:
            # If it's a value error, then the string 
            # is not a valid hex code for a UUID.
            return False

        # If the uuid_string is a valid hex code, 
        # but an invalid uuid4,
        # the UUID.__init__ will convert it to a 
        # valid uuid4. This is bad for validation purposes.
        return val.hex == userid

    def isregistereduser(self, a):
        """ check whether the user address is a registered one or generated one """
        return not self.valid_uuid4(a)
