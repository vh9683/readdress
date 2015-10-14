#! /usr/bin/python3.4

import uuid

OUR_DOMAIN = 'readdress.io'

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

