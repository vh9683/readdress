#! /usr/bin/python3.4
import configparser
import os

config_file = 'readdress_config.ini'

class ReConfig:
    def __init__(self):
        self.ignored_lists = list()
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.config_file = os.path.join(os.getcwd(), config_file)
        if not os.path.isfile(self.config_file):
            raise ValueError("MISSING Config file {}".format(config_file))

        try :
            print ("Reading config file {}".format(self.config_file))
            self.config.read( self.config_file )
        except:
            raise
        return

    def ConfigSectionMap(self, section):
        #print ("Sections : {}".format(self.config.sections()))
        if section == 'DEFAULT':
            return self.config.defaults()

        if section in self.config:
            return self.config[section]
        else:
            raise ValueError("Config Some thing worng for section {}".format(section))

    def get_ourdomain(self):
        return self.config.defaults().get('OUR_DOMAIN',None)
    
    def get_redis_mail_dump_exp_time(self):
        return int (self.config.defaults().get('REDIS_MAIL_DUMP_EXPIRY_TIME', '600') )

    def get_sendmail_key_exp_time(self):
        return int (self.config.defaults().get('SENDMAIL_KEY_EXPIRE_TIME', '300') )

    def get_verification_expire_time_secs(self):
        hrs = int (self.config.defaults().get('VERIFICATION_MAIL_EXP_TIME_IN_HRS', '20') )
        seconds = hrs * 60 * 60
        return seconds

    def get_verification_expire_time_hours(self):
        hrs = int (self.config.defaults().get('VERIFICATION_MAIL_EXP_TIME_IN_HRS', '20') )
        return hrs

    def get_noreply_name(self):
        return self.config.defaults().get('NOREPLY_NAME', None)

    def get_noreply_mailid(self):
        return self.config.defaults().get('NOREPLY_ADDRESS', None)

    def get_formatted_noreply(self):
        import email.utils
        return email.utils.formataddr( ( self.get_noreply_name(), self.get_noreply_mailid() ))

    def get_ignored_list(self):
        if len(self.ignored_lists) == 0 :
            res = self.ConfigSectionMap('APP')['IGNORED_MAIL_ROUTES']
            self.ignored_lists = res.split(',')
            self.ignored_lists = [ i.strip() for i in self.ignored_lists ]

        return self.ignored_lists

    def get_spf_allowed_results(self):
        res = self.ConfigSectionMap('APP')['SPF_ALLOWED_ON_DKIM_PASS']
        allowed_list = res.split(',')
        allowed_list = [ i.strip() for i in allowed_list]
        return allowed_list



            

