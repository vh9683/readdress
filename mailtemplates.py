readdrsignup = """<h3>Just One More step to Get Started</h3>
<h4>Click on the below link and follow instructions to complete verification</h4>
<h4>https://readdress.io/verify/{{sessionid}}</h4>

<h5>note: The above link is valid only for few minutes and for one time use only. Please do not forward this to anyone.</h5>

<h5>You have received this in response to mail sent to signup@readdress.io, If you haven't sent the mail, please ignore this and may be it is a good idea to change password of your email service</h5>"""


mailtemplates = {'readdrsignup': { 'subject': 'Verify to Get Started', 'template': readdrsignup, 'from_email': 'Readdress.io <noreply@readdress.io>'},
}

