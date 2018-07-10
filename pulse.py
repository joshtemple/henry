import logging
from spinner import Spinner
import logging
from tqdm import tqdm
from colors import Colors as colors
from tabulate import tabulate
from tqdm import trange
import re
import requests


class Pulse(object):

    postfix_default = [dict(value="RUNNING")]

    def __init__(self, looker):
        self.looker = looker
        self.pulse_logger = logging.getLogger(__name__)
        self.bar = '%s%s{postfix[0][value]}%s {desc}: ' \
                   '{percentage:3.0f}%% |{bar}|[{elapsed}<' \
                   '{remaining}]' % (colors.BOLD, colors.GREEN, colors.ENDC)
        self.postfix_default = [dict(value="RUNNING")]

    def run_all(self):
        self.pulse_logger.info('Checking instance pulse')
        self.pulse_logger.info('Checking Connections')
        result = self.check_connections()
        print(result, end='\n')
        self.pulse_logger.info('Complete: Checking Connections')

        self.pulse_logger.info('Analyzing Query Stats')
        r1, r2, r3 = self.check_query_stats()
        print(r1)
        print(r2)
        print(r3, end='\n\n')
        self.pulse_logger.info('Complete: Analyzing Query Stats')

        # check scheduled plans
        self.pulse_logger.info('Analyzing Query Stats')
        with trange(1, desc='(3/5) Analyzing Scheduled Plans',
                    bar_format=self.bar, postfix=self.postfix_default,
                    ncols=100, miniters=0) as t:
            for i in t:
                result = self.check_scheduled_plans()
                if type(result) == list and len(result) > 0:
                    result = tabulate(result, headers="keys",
                                      tablefmt='psql', numalign='center')
                t.postfix[0]["value"] = 'DONE'
                t.update()
        print(result, end='\n\n')
        self.pulse_logger.info('Complete: Analyzing Scheduled Plans')

        # check enabled legacy features
        self.pulse_logger.info('Checking Legacy Features')
        with trange(1, desc='(4/5) Legacy Features', bar_format=self.bar,
                    postfix=self.postfix_default, ncols=100, miniters=0) as t:
            for i in t:
                result = self.check_legacy_features()
                t.postfix[0]["value"] = 'DONE'
                t.update()
        print(result, end='\n\n')
        self.pulse_logger.info('Complete: Checking Legacy Features')

        # check looker version
        self.pulse_logger.info('Checking Version')
        t = trange(1, desc='(5/5) Version', bar_format=self.bar,
                   postfix=self.postfix_default, ncols=100)
        for i in t:
            result, status = self.check_version()
            t.postfix[0]["value"] = "DONE"
            t.update()
        print(result, end='\n\n')
        self.pulse_logger.info('Complete: Checking Version')
        self.pulse_logger.info('Complete: Checking instance pulse')

        return

    def check_connections(self):
        result = []
        connections = []
        for c in self.looker.get_connections():
            if c['name'] != 'looker':
                c_tests = (', ').join(c['dialect']['connection_tests'])
                c_name = c['name']
                connections.append((c_name, c_tests))

        with tqdm(total=len(connections), desc='(1/5) Testing Connections',
                  bar_format=self.bar, postfix=self.postfix_default,
                  ncols=100, miniters=0) as t:
            for idx, (c, tests) in enumerate(connections):
                tests = {'tests': tests}
                results = self.looker.test_connection(c, tests)
                formatted_results = []
                for i in results:
                    formatted_results.append(i['message'])
                formatted_results = list(set(formatted_results))
                status = ('\n').join(formatted_results)
                result.append({'name': c,
                               'status': status})
                if idx == len(connections)-1:
                    t.postfix[0]['value'] = 'DONE'
                t.update()

        return tabulate(result, tablefmt='psql')

    def check_query_stats(self):
        # check query stats
        with trange(3, desc='(2/5) Analyzing Query Stats', bar_format=self.bar,
                    postfix=self.postfix_default, ncols=100, miniters=0) as t:
            for i in t:
                if i == 0:
                    query_count = self.get_query_type_count()
                if i == 1:
                    query_runtime_stats = self.get_query_stats('complete')
                if i == 2:
                    query_queue_stats = self.get_query_stats('pending')
                    t.postfix[0]['value'] = 'DONE'

        r1 = '{} queries run, ' \
             '{} queued, ' \
             '{} errored, ' \
             '{} killed'.format(query_count['total'], query_count['queued'],
                                query_count['errored'], query_count['killed'])
        r2 = 'Query Runtime min/avg/max: ' \
             '{}/{}/{} seconds'.format(query_runtime_stats['min'],
                                       query_runtime_stats['avg'],
                                       query_runtime_stats['max'])
        r3 = 'Queuing time min/avg/max: ' \
             '{}/{}/{}'.format(query_queue_stats['min'],
                               query_queue_stats['avg'],
                               query_queue_stats['max'])

        return r1, r2, r3

    # get number of queries run, killed, completed, errored, queued
    def get_query_type_count(self):
        body = {
                "model": "i__looker",
                "view": "history",
                "fields": [
                    "history.query_run_count",
                    "history.status",
                    "history.created_date"
                    ],
                "pivots": [
                    "history.status"
                    ],
                "filters": {
                    "history.created_date": "30 days",
                    "history.status": "-NULL",
                    "history.result_source": "query",
                    "query.model": "-i^_^_looker"
                },
                "sorts": [
                    "history.created_date desc",
                    "history.result_source"
                    ],
                "limit": "50000"
                }

        r = self.looker.run_inline_query(result_format="json", body=body,
                                         fields={"cache": "false"})
        completed = 0
        errored = 0
        killed = 0
        queued = 0
        if(len(r) > 0):
            for entry in r:
                e = entry['history.query_run_count']['history.status']
                if 'complete' in e:
                    c_i = e['complete']
                else:
                    c_i = 0
                c_i = c_i if c_i is not None else 0
                completed += c_i

                if 'error' in e:
                    e_i = e['error']
                else:
                    e_i = 0
                e_i = e_i if e_i is not None else 0
                errored += e_i

                if 'killed' in e:
                    k_i = e['killed']
                else:
                    k_i = 0
                k_i = k_i if k_i is not None else 0
                killed += k_i

                if 'pending' in e:
                    q_i = e['pending']
                else:
                    q_i = 0
                q_i = q_i if q_i is not None else 0
                queued += q_i

        response = {'total': completed+errored+killed,
                    'completed': completed,
                    'errored': errored,
                    'killed': killed,
                    'queued': queued}

        return response

    # get number of queries run, killed, completed, errored, queued
    def get_query_stats(self, status):
        valid_statuses = ['error', 'complete', 'pending', 'running']
        if status not in valid_statuses:
            raise ValueError("Invalid query status, must be in %r"
                             % valid_statuses)
        body = {
                "model": "i__looker",
                "view": "history",
                "fields": [
                    "history.min_runtime",
                    "history.max_runtime",
                    "history.average_runtime",
                    "history.total_runtime"
                    ],
                "filters": {
                    "history.created_date": "30 days",
                    "history.status": status,
                    "query.model": "-i^_^_looker"
                },
                "limit": "50000"
                }

        r = self.looker.run_inline_query(result_format="json", body=body,
                                         fields={"cache": "false"})[0]
        for i in ('history.min_runtime',
                  'history.max_runtime',
                  'history.average_runtime'):
            if r[i] is not None:
                r[i] = round(r[i], 2)
            else:
                r[i] = '-'
        response = {'min': r['history.min_runtime'],
                    'max': r['history.max_runtime'],
                    'avg': r['history.average_runtime'],
                    'total': r['history.total_runtime']}

        return response

    def check_scheduled_plans(self):
        body = {
                "model": "i__looker",
                "view": "scheduled_plan",
                "fields": ["scheduled_job.status", "scheduled_job.count"],
                "pivots": ["scheduled_job.status"],
                "filters": {
                            "scheduled_plan.run_once": "no",
                            "scheduled_job.status": "-NULL",
                            "scheduled_job.created_date": "30 days"
                           },
                "limit": "50000"
                }

        r = self.looker.run_inline_query("json", body)
        result = []
        if r:
            r = r[0]['scheduled_job.count']['scheduled_job.status']
            failed = r['failure'] or 0
            succeeded = r['success'] or 0
            result.append({'total': failed+succeeded,
                           'failure': failed,
                           'success': succeeded})
            return result
        else:
            return "No Plans Found"

    def check_integrations(self):
        response = self.looker.get_integrations()
        integrations = []
        for r in response:
            if r['enabled']:
                integrations.append(r['label'])

        result = None if len(integrations) == 0 else integrations

        return result

    def check_legacy_features(self):
        response = self.looker.get_legacy_features()
        _result = []
        for r in response:
            if r['enabled'] is True:
                _result.append({'Legacy Features' : r['name']})

        if _result:
            result = tabulate(_result, headers="keys", tablefmt='psql')
        else:
            result = 'No legacy features found'
        return result

    def check_version(self):
        _v = self.looker.get_version()['looker_release_version']
        version = re.findall(r'(\d.\d+)', _v)[0]
        session = requests.Session()
        _lv = session.get('https://learn.looker.com:19999/versions').json()
        _lv = _lv['looker_release_version']
        latest_version = re.findall(r'(\d.\d+)', _lv)[0]
        if version == latest_version:
            return version, "up-to-date"
        else:
            return version, "outdated"
