import json
import logging
import traceback
import pprint
import socket
import time
from smtplib import SMTPException
from django.core.mail import mail_admins
from django.db import transaction
from oioioi.contests.models import Contest, ProblemInstance, Submission, \
        SubmissionReport, FailureReport

logger = logging.getLogger(__name__)


WAIT_FOR_SUBMISSION_RETRIES = 9
WAIT_FOR_SUBMISSION_SLEEP_SECONDS = 1


def wait_for_submission_in_db(env, **kwargs):
    """Celery may start handling a submission before it is actually saved
       in the DB. This is a workaround for this.
    """
    for _i in xrange(WAIT_FOR_SUBMISSION_RETRIES):
        with transaction.atomic():
            if bool(Submission.objects.filter(id=env['submission_id'])):
                break
        time.sleep(WAIT_FOR_SUBMISSION_SLEEP_SECONDS)
    return env


@transaction.atomic
def update_report_statuses(env, **kwargs):
    submission = Submission.objects.get(id=env['submission_id'])
    problem_instance = submission.problem_instance
    reports = SubmissionReport.objects.filter(submission=submission)
    problem_instance.controller.update_report_statuses(submission, reports)
    return env


@transaction.atomic
def update_submission_score(env, **kwargs):
    submission = Submission.objects.get(id=env['submission_id'])
    problem_instance = submission.problem_instance
    problem_instance.controller.update_submission_score(submission)
    return env


def update_user_results(env, **kwargs):
    with transaction.atomic():
        submission = Submission.objects.get(id=env['submission_id'])
        user = submission.user
        if not user:
            return env
        problem_instance = \
                ProblemInstance.objects.get(id=env['problem_instance_id'])
        round = problem_instance.round
        contest = None
        if round is not None:
            assert round.id == env['round_id']
            contest = round.contest
            assert contest.id == env['contest_id']
        else:
            assert 'round_id' not in env
            assert 'contest_id' not in env

    problem_instance.controller.update_user_results(user, problem_instance)

    return env


@transaction.atomic
def call_submission_judged(env, **kwargs):
    submission = Submission.objects.get(id=env['submission_id'])
    contest = submission.problem_instance.contest

    if contest is None:
        assert 'contest_id' not in env
        return env

    assert contest.id == env['contest_id']
    contest.controller.submission_judged(submission,
            rejudged=env['is_rejudge'])
    contest.controller.submission_unqueued(submission, env['job_id'])
    return env


@transaction.atomic
def create_error_report(env, exc_info, **kwargs):
    """Builds a :class:`oioioi.contests.models.SubmissionReport` for
       an evaulation which have failed.

       USES
           * `env['submission_id']`
    """

    logger.error("System Error evaluating submission #%s:\n%s",
            env.get('submission_id', '???'),
            pprint.pformat(env, indent=4), exc_info=exc_info)

    if 'submission_id' not in env:
        return env

    try:
        submission = Submission.objects.get(id=env['submission_id'])
    except Submission.DoesNotExist:
        return env

    submission_report = SubmissionReport(submission=submission)
    submission_report.kind = 'FAILURE'
    submission_report.save()

    failure_report = FailureReport(submission_report=submission_report)
    failure_report.json_environ = json.dumps(env)
    failure_report.message = traceback.format_exc(exc_info)
    failure_report.save()

    return env


def mail_admins_on_error(env, exc_info, **kwargs):
    """Sends email to all admins defined in settings.ADMINS on each
       grading error occurrence.

       USES
           * `env['submission_id']`
    """

    # We don't want to spam admins when the evaluation of a deleted
    # submission fails. See also SIO-1254.
    try:
        if 'submission_id' in env:
            Submission.objects.get(id=env['submission_id'])
    except Submission.DoesNotExist:
        return env

    try:
        mail_admins("System Error evaluating submission #%s" %
                    env.get('submission_id', '???'),
                    traceback.format_exc(exc_info))
    except (socket.error, SMTPException), e:
        logger.error("An error occurred while sending email: %s",
                     e.message)

    return env
