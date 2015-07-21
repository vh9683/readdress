# This is main codebase #
## Be sure to save your work and ##

## Design decisions ##

Assumptions: From address will not our own

Scenario 1:
A and B are registered users with 1 and 2 being there numbers
C is the sender

first post to us will have
from: C
To: 1,2

We loop through the receipents and for each registered user found:
  get the mapped mail id: 1 -> A, 2 -> B
  transform the from address to our domain: C -> 3 (this is a base64 encoded id, so can be distinguished from other registered addresses)
  send mail including the transformed from address and other recepients in To header
  the actual recepient will be the mapped mail id

  Recepient: A
  From: 3
  To: 2

  Recepient: B
  From: 3
  To: 1

Now if A or B "reply" to mail, we receive a post like
  To: 3
  From: A

  If we apply the logic as before
  We loop through the receipents and for each registered user found:
  get the mapped mail id: 3 -> C
  transform the from address to our domain: A -> 1 (we detect that A is a registered user and so this is a reply)
  send mail including the transformed from address and other recepients in To header
  the actual recepient will be the mapped mail id

  Recepient: C
  From: 1
  
Now if A does "reply all", we receive a post like
  To: 2, 3
  From: A

  If we apply the logic as before
  We loop through the receipents and for each registered user found:
  get the mapped mail id: 3 -> C, 2 -> B
  transform the from address to our domain: A -> 1 (we detect that A is a registered user and so this is a reply)
  send mail including the transformed from address and other recepients in To header
  the actual recepient will be the mapped mail id

  Recepient: C
  From: 1
  To: 2

  Recepient: B
  From: 1
  To: 3


