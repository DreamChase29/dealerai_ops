# Synthetic Service Scheduling Guide

Fictional/synthetic demonstration material for DealerAI Ops. This content is not real scheduling
policy and must be validated before real use.

## Scheduling Channels

Customers may request service appointments through web chat, phone, SMS, email, or a service advisor.
Web and SMS requests should collect customer ID, vehicle ID, requested service type, preferred time
window, and contact method.

## Slot Capacity

Service slots have a bay type, advisor, start time, end time, capacity, and booked count. A slot is
available only when booked count is lower than capacity. Booking must reserve capacity transactionally.

## Booking Confirmation

Appointment booking is a high-risk write operation. The system must receive explicit confirmation
before booking a service appointment. If confirmation is missing, the tool should return a confirmation
required response and avoid mutating data.

## Rescheduling

Rescheduling an appointment requires explicit confirmation. The previous slot capacity should be
released when the appointment moves to a different slot. The new slot must have remaining capacity and
must start in the future.

## Cancellation

Cancellation requires explicit confirmation. Canceling a scheduled or confirmed appointment releases
the associated slot capacity. Completed appointments cannot be canceled.

## Reminder Strategy

Reminder intensity may be adjusted using booking lead time, channel, prior no-show count, appointment
type, and predicted no-show risk. Very high-risk appointments should be considered for advisor
follow-up.
