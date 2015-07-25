# Transaction #

## There are three headers that need to be checked ##
### 1. Message-Id ###
### 2. In-Reply-To ###
### 3. References ###

#### Message-Id: This is the id for this message, so this needs to be always added to db ####

#### In-Reply-To: This could have the id of the message to which this is reply, so this should be checked first and id mentioned should already be in the db ####

#### References: This could have the id of all the messages in the chain , so this should be checked second and id mentioned should already be in the db ####

## Purpose ##

### 1. To make sure only registered users start a new thread ###
#### If In-Reply-To is not present and References only contains Message-Id or is not present, then the from address should be from known domain and
To list should contain at leadt one registered user ####
### If above condition is met, Message-Id is saved in db ###
### 2. To make sure replies are for known thread ###
#### If In-Reply-To is present, the Message-Id mentioned should be present in db ####
### If above condition is met, In-Reply-To is saved in db ###
#### If References is present, the Message-Id mentioned should be present in db, any unknown References can be ignored for now, may be later we can mark this as suspicious or spam ####
### 3. To list can be saved to db and checked for new members being added to thread ###