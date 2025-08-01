import pytz
import logging
from odoo import models, fields
from datetime import timedelta
from odoo.tools import html2plaintext

try:
    import vobject
except ImportError:
    _logger.warning("`vobject` Python module not found, iCal file generation disabled. Consider installing this module if you want to generate iCal files")
    vobject = None


class CarRentalCalendarEvent(models.Model):
    """Inherit calendar.event"""
    _inherit = 'calendar.event'

    def _get_ics_file(self):
        """ Returns iCalendar file for the event invitation.
            :returns a dict of .ics file content for each meeting
        """
        result = {}

        def ics_datetime(idate, allday=False):
            if idate:
                if allday:
                    return idate
                return idate.replace(tzinfo=pytz.timezone('UTC'))
            return False

        if not vobject:
            return result

        for meeting in self:
            cal = vobject.iCalendar()
            event = cal.add('vevent')

            if not meeting.start or not meeting.stop:
                raise UserError(_("First you have to specify the date of the invitation."))

            event.add('uid').value = f"{meeting.id}@5fe393a9-25de-4abf-99d1-9513ac258051"
            event.add('created').value = ics_datetime(fields.Datetime.now())
            event.add('dtstart').value = ics_datetime(meeting.start, meeting.allday)
            event.add('dtend').value = ics_datetime(meeting.stop, meeting.allday)
            event.add('summary').value = meeting._get_customer_summary()
            description = html2plaintext(meeting._get_customer_description())
            if description:
                event.add('description').value = description
            if meeting.location:
                event.add('location').value = meeting.location
            if meeting.rrule:
                event.add('rrule').value = meeting.rrule

            if meeting.alarm_ids:
                for alarm in meeting.alarm_ids:
                    valarm = event.add('valarm')
                    interval = alarm.interval
                    duration = alarm.duration
                    trigger = valarm.add('TRIGGER')
                    trigger.params['related'] = ["START"]
                    if interval == 'days':
                        delta = timedelta(days=duration)
                    elif interval == 'hours':
                        delta = timedelta(hours=duration)
                    elif interval == 'minutes':
                        delta = timedelta(minutes=duration)
                    trigger.value = delta
                    valarm.add('DESCRIPTION').value = alarm.name or u'Odoo'
            for attendee in meeting.attendee_ids:
                attendee_add = event.add('attendee')
                attendee_add.value = u'MAILTO:' + (attendee.email or u'')

            # Add "organizer" field if email available
            if meeting.partner_id.email:
                organizer = event.add('organizer')
                organizer.value = u'MAILTO:' + meeting.partner_id.email
                if meeting.partner_id.name:
                    organizer.params['CN'] = [meeting.partner_id.display_name.replace('\"', '\'')]

            result[meeting.id] = cal.serialize().encode('utf-8')

        return result
