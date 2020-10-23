import os
from sendgrid import *
from sendgrid.helpers.mail import Mail

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def SendInviteEmail(username, name, password, email):

    try:

        logger.info(
            f"SendInviteEmail() - Sending invitation to {email}.")

        api_key = os.environ.get('SENDGRID_API_KEY')

        if not api_key:
            logger.error(
                "SendInviteEmail() - NO SEND GRID API KEY. Please add a SENDGRID_API_KEY to .django env variable file.")

        else:
            sg = sendgrid.SendGridAPIClient(api_key=api_key)
            from_email = Email("test@example.com")
            to_email = To(email)
            subject = 'Welcome to GREMLIN - The Low-Code Microservices Framework'
            content = Content("text/plain", f"Dear {name},\n\nWelcome to GREMLIN. Your login details are as follows.\n\n\tUsername: {username}\n\tPassword:"
                 f" {password}\n\nYou can change your password by going to the Settings tab and clicking 'Change Password'.")
            mail = Mail(from_email, to_email, subject, content)
            response = sg.client.mail.send.post(request_body=mail.get())
            logger.info(
                f"SendInviteEmail() - Done with status of {response.status_code}.")

    except Exception as e:
        logger.error("Error trying to send invite e-mail:")
        logger.error(e.message if e.message else e)
        return False

    return True

def SendResetPasswordEmail(username, name, password, email):

    try:

        logger.info(
            f"SendResetPasswordEmail() - Sending password email to {email}.")

        api_key = os.environ.get('SENDGRID_API_KEY')

        if not api_key:
            logger.error(
                "SendResetPasswordEmail() - NO SEND GRID API KEY. Please add a SENDGRID_API_KEY to .django env variable file.")

        else:

            sg = sendgrid.SendGridAPIClient(api_key=api_key)
            from_email = Email("test@example.com")
            to_email = To(email)
            subject = 'GREMLIN - Password Reset'
            content = Content("text/plain", f"Dear {name},\n\nYour password has been reset. Your login details are as follows.\n\n\tUsername: {username}\n\tPassword:"
                 f" {password}\n\nYou can change your password by going to the Settings tab and clicking 'Change Password'.")
            mail = Mail(from_email, to_email, subject, content)
            response = sg.client.mail.send.post(request_body=mail.get())

            logger.info(
                f"SendResetPasswordEmail() - Done with status of {response.status_code}.")

    except Exception as e:
        logger.error("Error trying to send password reset email:")
        logger.error(e.message if e.message else e)
        return False

    return True

def SendUsernameEmail(username, name, email):

    try:

        logger.info(
            f"SendUsernameEmail() - Sending username to {email}.")

        api_key = os.environ.get('SENDGRID_API_KEY')

        if not api_key:
            logger.error(
                "SendUsernameEmail() - NO SEND GRID API KEY. Please add a SENDGRID_API_KEY to .django env variable file.")

        else:
            sg = sendgrid.SendGridAPIClient(api_key=api_key)
            from_email = Email("test@example.com")
            to_email = To(email)
            subject = 'GREMLIN - Your Username'
            content = Content("text/plain", f"Dear {name}, your username is {username}.")
            mail = Mail(from_email, to_email, subject, content)
            response = sg.client.mail.send.post(request_body=mail.get())
            logger.info(
                f"SendUsernameEmail() - Done with status of {response.status_code}.")

    except Exception as e:
        logger.error("SendUsernameEmail - Error trying to send username reminder email:")
        logger.error(e.message if e.message else e)
        return False

    return True

def SendJobFinishedEmail(email, username, job_status, job_name, pipeline_name, pipeline_description):
    try:

        logger.info(
            f"SendJobFinishedEmail() - Sending job notification {job_name} is complete to {email}.")

        api_key = os.environ.get('SENDGRID_API_KEY')

        if not api_key:
            logger.error(
                "SendJobFinishedEmail() - NO SEND GRID API KEY. Please add a SENDGRID_API_KEY to .django env variable file.")

        else:
            sg = sendgrid.SendGridAPIClient(api_key=api_key)
            from_email = Email("test@example.com")
            to_email = To(email)
            subject = f'GREMLIN - {job_name} - Status: {job_status}'
            content = Content("text/plain", f"{username},\n\n{job_name} has finished.\n\n\tStatus: {job_status}"
                                            f"\n\tAnalyzer Type: {pipeline_name}\n\tAnalyzer Description: {pipeline_description}")
            mail = Mail(from_email, to_email, subject, content)
            response = sg.client.mail.send.post(request_body=mail.get())
            logger.info(
                f"SendJobFinishedEmail() - Done with status of {response.status_code}.")

    except Exception as e:
        logger.error("SendJobFinishedEmail() - Error trying to send username reminder email:")
        logger.error(e.message if e.message else e)
        return False

    return True
