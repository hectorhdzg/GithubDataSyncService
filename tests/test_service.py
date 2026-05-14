"""
Unit tests for GitHub Sync Service

Uses isolated GitHubSyncService instances backed by per-test temp databases
and mocks for external dependencies (GitHub API, scheduler).
"""

import unittest
import sys
import os
import tempfile
import sqlite3
import json
from unittest.mock import patch, MagicMock

# Add src to path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Patch DATABASE_PATH before importing app so the module-level service
# initializes against a disposable temp DB.
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix='.db')
os.close(_test_db_fd)
os.environ['DATABASE_PATH'] = _test_db_path

from app import app, GitHubSyncService, sync_service

# Shut down the background scheduler immediately — tests don't need it and
# it causes "database is locked" errors.
if sync_service.scheduler.running:
    sync_service.scheduler.shutdown(wait=False)


def _make_service(db_path=None):
    """Create an isolated GitHubSyncService with its own temp DB and no scheduler."""
    if db_path is None:
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

    with patch.object(GitHubSyncService, '_setup_automatic_sync'):
        svc = GitHubSyncService(db_path)
    # Give tests the path so they can clean up or inspect
    svc._test_db_path = db_path
    return svc


# =========================================================================
# Base class for Flask endpoint tests (shared test client, uses module DB)
# =========================================================================
class TestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()


# =========================================================================
# Base class for service-method unit tests (each test gets its own DB)
# =========================================================================
class TestServiceBase(unittest.TestCase):

    def setUp(self):
        self.svc = _make_service()

    def tearDown(self):
        try:
            os.unlink(self.svc._test_db_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Health & metadata endpoints
# ---------------------------------------------------------------------------
class TestHealthEndpoints(TestBase):

    def test_health_check(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('timestamp', data)
        self.assertIn('requests_available', data)

    def test_statistics(self):
        response = self.client.get('/api/statistics')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('total_issues', data)
        self.assertIn('total_prs', data)
        self.assertIn('total_repositories', data)
        self.assertIn('last_sync', data)

    def test_stats(self):
        response = self.client.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        stats = data['stats']
        self.assertIn('repositories', stats)
        self.assertIn('total_issues', stats)
        self.assertIn('total_pull_requests', stats)
        self.assertIn('issues_by_state', stats)
        self.assertIn('recent_activity', stats)


# ---------------------------------------------------------------------------
# Repository CRUD
# ---------------------------------------------------------------------------
class TestRepositories(TestBase):

    def test_list_repositories(self):
        response = self.client.get('/api/repositories')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['repositories'], list)
        self.assertIn('stats', data)

    def test_list_repositories_with_inactive(self):
        response = self.client.get('/api/repositories?includeInactive=true')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])

    def test_list_repositories_with_filters(self):
        response = self.client.get('/api/repositories?includeFilters=true')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        for repo in data['repositories']:
            self.assertIn('filters', repo)

    def test_add_repository_missing_fields(self):
        response = self.client.post('/api/repositories',
                                    data=json.dumps({'repo': 'owner/name'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    @patch.object(GitHubSyncService, '_validate_repository_on_github',
                  return_value=(True, {'full_name': 'test/repo', 'language': 'Python',
                                       'owner': {'login': 'test'}}, None))
    def test_add_and_remove_repository(self, _mock_validate):
        payload = {
            'repo': 'test/test-repo-crud',
            'display_name': 'Test Repo',
            'main_category': 'Test',
            'classification': 'Python',
            'priority': 5,
        }
        # Add
        response = self.client.post('/api/repositories',
                                    data=json.dumps(payload),
                                    content_type='application/json')
        self.assertIn(response.status_code, (200, 201))
        data = response.get_json()
        self.assertTrue(data['success'])

        # Duplicate should fail
        response = self.client.post('/api/repositories',
                                    data=json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # Remove
        response = self.client.delete('/api/repositories/test/test-repo-crud')
        self.assertEqual(response.status_code, 200)

    def test_remove_nonexistent_repository(self):
        response = self.client.delete('/api/repositories/nonexistent/repo')
        self.assertEqual(response.status_code, 400)

    @patch.object(GitHubSyncService, '_validate_repository_on_github',
                  return_value=(True, {'full_name': 'test/upd', 'language': 'Go',
                                       'owner': {'login': 'test'}}, None))
    def test_update_repository(self, _mock):
        payload = {
            'repo': 'test/update-target',
            'display_name': 'Update Me',
            'main_category': 'Test',
            'classification': 'Go',
            'priority': 3,
        }
        self.client.post('/api/repositories',
                         data=json.dumps(payload),
                         content_type='application/json')

        response = self.client.put('/api/repositories/test/update-target',
                                   data=json.dumps({'display_name': 'Updated'}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])

        self.client.delete('/api/repositories/test/update-target')

    def test_update_nonexistent_repository(self):
        response = self.client.put('/api/repositories/no/such',
                                   data=json.dumps({'display_name': 'X'}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# Repository filters
# ---------------------------------------------------------------------------
class TestRepositoryFilters(TestBase):

    def test_get_filters_for_seeded_repo(self):
        repos_resp = self.client.get('/api/repositories')
        repos = repos_resp.get_json()['repositories']
        if repos:
            repo_name = repos[0]['repo']
            response = self.client.get(f'/api/repositories/{repo_name}/filters')
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data['success'])
            self.assertIn('filters', data)

    @patch.object(GitHubSyncService, '_validate_repository_on_github',
                  return_value=(True, {'full_name': 'test/f', 'language': 'Python',
                                       'owner': {'login': 'test'}}, None))
    def test_update_filters(self, _mock):
        self.client.post('/api/repositories',
                         data=json.dumps({
                             'repo': 'test/filter-target',
                             'display_name': 'Filter Test',
                             'main_category': 'Test',
                             'classification': 'Python',
                             'priority': 5,
                         }),
                         content_type='application/json')

        new_filters = {'issues': {'state': 'open', 'labels': ['bug']}}
        response = self.client.put('/api/repositories/test/filter-target/filters',
                                   data=json.dumps({'filters': new_filters}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])

        response = self.client.get('/api/repositories/test/filter-target/filters')
        data = response.get_json()
        self.assertEqual(data['filters']['issues']['state'], 'open')

        self.client.delete('/api/repositories/test/filter-target')

    def test_update_filters_nonexistent_repo(self):
        response = self.client.put('/api/repositories/no/repo/filters',
                                   data=json.dumps({'filters': {}}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Issues & PR data endpoints
# ---------------------------------------------------------------------------
class TestDataEndpoints(TestBase):

    def test_get_issues_empty(self):
        response = self.client.get('/api/issues')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['issues'], list)

    def test_get_issues_with_params(self):
        response = self.client.get('/api/issues?repository=fake/repo&state=open&limit=5')
        self.assertEqual(response.status_code, 200)

    def test_get_pull_requests_empty(self):
        response = self.client.get('/api/pull_requests')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['pull_requests'], list)

    def test_get_pull_requests_with_params(self):
        response = self.client.get('/api/pull_requests?repository=fake/repo&state=closed&limit=5')
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------
class TestSyncEndpoints(TestBase):

    def test_sync_status(self):
        response = self.client.get('/api/sync/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('sync_status', data)

    def test_sync_history(self):
        response = self.client.get('/api/sync/history')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('sync_history', data)
        self.assertIsInstance(data['sync_history'], list)

    def test_sync_history_with_limit(self):
        response = self.client.get('/api/sync/history?limit=5')
        self.assertEqual(response.status_code, 200)

    def test_data_freshness(self):
        response = self.client.get('/api/data/freshness')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('freshness', data)

    def test_sample_sync_history(self):
        response = self.client.post('/api/sync/history/sample')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('session_id', data)


# ---------------------------------------------------------------------------
# Scheduler endpoints
# ---------------------------------------------------------------------------
class TestScheduler(TestBase):

    def test_scheduler_status(self):
        response = self.client.get('/api/scheduler/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('running', data)
        self.assertIn('enabled', data)


# ---------------------------------------------------------------------------
# Service-level unit tests — isolated DB per test, no scheduler, mocked I/O
# ---------------------------------------------------------------------------
class TestNormalization(TestServiceBase):

    def test_normalize_valid(self):
        self.assertEqual(self.svc._normalize_repository_identifier('owner/repo'), 'owner/repo')

    def test_normalize_with_whitespace(self):
        self.assertEqual(self.svc._normalize_repository_identifier(' owner / repo '), 'owner/repo')

    def test_normalize_missing_slash(self):
        with self.assertRaises(ValueError):
            self.svc._normalize_repository_identifier('noslash')

    def test_normalize_empty(self):
        with self.assertRaises(ValueError):
            self.svc._normalize_repository_identifier('')

    def test_normalize_slash_only(self):
        with self.assertRaises(ValueError):
            self.svc._normalize_repository_identifier('/')


class TestParseIsoDatetime(TestServiceBase):

    def test_parse_iso_with_z(self):
        dt = self.svc._parse_iso_datetime('2024-01-15T10:30:00Z')
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 10)

    def test_parse_iso_with_offset(self):
        dt = self.svc._parse_iso_datetime('2024-01-15T10:30:00+05:00')
        self.assertIsNotNone(dt)

    def test_parse_iso_none(self):
        self.assertIsNone(self.svc._parse_iso_datetime(None))

    def test_parse_iso_empty(self):
        self.assertIsNone(self.svc._parse_iso_datetime(''))

    def test_parse_iso_invalid(self):
        self.assertIsNone(self.svc._parse_iso_datetime('not-a-date'))


class TestLanguageGroup(TestServiceBase):

    def test_dotnet(self):
        self.assertEqual(self.svc._determine_language_group('r', 'd', '.NET', 'cat'), 'DotNet')

    def test_python(self):
        self.assertEqual(self.svc._determine_language_group('r', 'd', 'Python', 'cat'), 'Python')

    def test_java(self):
        self.assertEqual(self.svc._determine_language_group('r', 'd', 'Java', 'cat'), 'Java')

    def test_node_override(self):
        result = self.svc._determine_language_group(
            'microsoft/applicationinsights-node.js', 'App Insights Node', 'JavaScript', 'AI'
        )
        self.assertEqual(result, 'Node.js')

    def test_browser_override(self):
        result = self.svc._determine_language_group(
            'microsoft/applicationinsights-js', 'App Insights JS', 'JavaScript', 'AI'
        )
        self.assertEqual(result, 'Web/Browser')

    def test_js_node_keyword(self):
        result = self.svc._determine_language_group('some/node-lib', 'Node Lib', 'JavaScript', 'cat')
        self.assertEqual(result, 'Node.js')

    def test_js_browser_keyword(self):
        result = self.svc._determine_language_group('some/react-app', 'React App', 'JavaScript', 'cat')
        self.assertEqual(result, 'Web/Browser')

    def test_js_generic(self):
        result = self.svc._determine_language_group('some/tool', 'Tool', 'JavaScript', 'cat')
        self.assertEqual(result, 'JavaScript')

    def test_unknown(self):
        self.assertEqual(self.svc._determine_language_group('r', 'd', '', ''), 'Other')


class TestBuildGithubApiParams(TestServiceBase):

    def test_state(self):
        params = self.svc.build_github_api_params({'issues': {'state': 'open'}}, 'issues')
        self.assertEqual(params['state'], 'open')

    def test_labels(self):
        params = self.svc.build_github_api_params({'issues': {'labels': ['bug', 'help wanted']}}, 'issues')
        self.assertEqual(params['labels'], 'bug,help wanted')

    def test_empty(self):
        self.assertEqual(self.svc.build_github_api_params({}, 'issues'), {})

    def test_all_fields(self):
        filters = {'pull_requests': {
            'state': 'closed', 'labels': ['ready'], 'assignee': 'user1',
            'milestone': '1.0', 'creator': 'author', 'sort': 'created', 'direction': 'asc',
        }}
        params = self.svc.build_github_api_params(filters, 'pull_requests')
        self.assertEqual(params['state'], 'closed')
        self.assertEqual(params['assignee'], 'user1')
        self.assertEqual(params['sort'], 'created')


class TestShouldExcludeItem(TestServiceBase):

    def test_exclude_by_label(self):
        item = {'labels': [{'name': 'duplicate'}], 'assignees': []}
        self.assertTrue(self.svc.should_exclude_item(item, {'issues': {'exclude_labels': ['duplicate']}}, 'issues'))

    def test_exclude_required_label_missing(self):
        item = {'labels': [{'name': 'other'}], 'assignees': []}
        self.assertTrue(self.svc.should_exclude_item(item, {'issues': {'labels': ['bug']}}, 'issues'))

    def test_exclude_required_label_present(self):
        item = {'labels': [{'name': 'bug'}], 'assignees': []}
        self.assertFalse(self.svc.should_exclude_item(item, {'issues': {'labels': ['bug']}}, 'issues'))

    def test_no_exclusion(self):
        item = {'labels': [{'name': 'enhancement'}], 'assignees': []}
        self.assertFalse(self.svc.should_exclude_item(item, {'issues': {'exclude_labels': ['duplicate']}}, 'issues'))

    def test_exclude_by_assignee(self):
        item = {'labels': [], 'assignees': [{'login': 'bot'}], 'assignee': None}
        self.assertTrue(self.svc.should_exclude_item(item, {'issues': {'exclude_assignees': ['bot']}}, 'issues'))

    def test_empty_filters(self):
        self.assertFalse(self.svc.should_exclude_item({'labels': [], 'assignees': []}, {}, 'issues'))


class TestConditionalHeaders(TestServiceBase):

    def test_with_timestamp(self):
        headers = self.svc._build_conditional_headers('2024-06-01T00:00:00Z')
        self.assertIn('If-Modified-Since', headers)

    def test_without_timestamp(self):
        headers = self.svc._build_conditional_headers(None)
        self.assertNotIn('If-Modified-Since', headers)


class TestSyncMetadata(TestServiceBase):

    def test_roundtrip(self):
        self.svc._update_sync_metadata(
            repository='test/meta-repo', sync_type='issues', status='success',
            items_synced=10, last_synced_at='2024-06-01T12:00:00Z',
        )
        ts = self.svc._get_last_sync_timestamp('test/meta-repo', 'issues')
        self.assertEqual(ts, '2024-06-01T12:00:00Z')

    def test_update_existing(self):
        self.svc._update_sync_metadata(
            repository='test/meta2', sync_type='prs', status='success',
            items_synced=5, last_synced_at='2024-01-01T00:00:00Z',
        )
        self.svc._update_sync_metadata(
            repository='test/meta2', sync_type='prs', status='success',
            items_synced=8, last_synced_at='2024-06-01T00:00:00Z',
        )
        ts = self.svc._get_last_sync_timestamp('test/meta2', 'prs')
        self.assertEqual(ts, '2024-06-01T00:00:00Z')

    def test_missing_returns_none(self):
        self.assertIsNone(self.svc._get_last_sync_timestamp('no/repo', 'issues'))


class TestSyncHistory(TestServiceBase):

    def test_record_and_get(self):
        self.svc.record_sync_history(
            sync_session_id='sess-1', repository='test/repo',
            sync_type='issues', issues_new=5, issues_updated=2,
            issues_total=7, duration_seconds=3, status='success',
        )
        history = self.svc.get_sync_history(limit=50)
        matching = [h for h in history if h['sync_session_id'] == 'sess-1']
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['issues_new'], 5)

    def test_empty_history(self):
        self.assertEqual(self.svc.get_sync_history(), [])


class TestRepositoryFiltersService(TestServiceBase):

    def test_default_for_unknown_repo(self):
        filters = self.svc.get_repository_filters('nonexistent/repo')
        self.assertIn('issues', filters)
        self.assertEqual(filters['issues']['state'], 'all')


class TestSyncIssues(TestServiceBase):
    """Test sync_repository_issues with mocked GitHub API responses."""

    @patch('app.requests')
    def test_sync_issues_success(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                'number': 1, 'title': 'Bug report', 'html_url': 'https://github.com/test/repo/issues/1',
                'created_at': '2024-01-01T00:00:00Z', 'updated_at': '2024-06-01T00:00:00Z',
                'state': 'open', 'body': 'A bug', 'labels': [{'name': 'bug'}],
                'assignees': [], 'assignee': None, 'comments': 2,
                'user': {'login': 'testuser', 'avatar_url': 'https://example.com/avatar.png'},
            }
        ]
        mock_requests.get.return_value = mock_response

        result = self.svc.sync_repository_issues('test/repo')
        self.assertTrue(result['success'])
        self.assertEqual(result['issues_new'], 1)
        mock_requests.get.assert_called_once()

    @patch('app.requests')
    def test_sync_issues_304_not_modified(self, mock_requests):
        # Seed a prior sync timestamp
        self.svc._update_sync_metadata(
            repository='test/repo', sync_type='issues', status='success',
            items_synced=0, last_synced_at='2024-01-01T00:00:00Z',
        )
        mock_response = MagicMock()
        mock_response.status_code = 304
        mock_requests.get.return_value = mock_response

        result = self.svc.sync_repository_issues('test/repo')
        self.assertTrue(result['success'])
        self.assertEqual(result['issues_synced'], 0)

    @patch('app.requests')
    def test_sync_issues_filters_pull_requests(self, mock_requests):
        """Items with a 'pull_request' key should be filtered out of issue sync."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                'number': 10, 'title': 'PR disguised as issue',
                'html_url': 'https://github.com/test/repo/pull/10',
                'created_at': '2024-01-01T00:00:00Z', 'updated_at': '2024-06-01T00:00:00Z',
                'state': 'open', 'body': '', 'labels': [], 'assignees': [],
                'assignee': None, 'comments': 0,
                'user': {'login': 'u', 'avatar_url': 'https://example.com/a.png'},
                'pull_request': {'url': 'https://api.github.com/repos/test/repo/pulls/10'},
            }
        ]
        mock_requests.get.return_value = mock_response

        result = self.svc.sync_repository_issues('test/repo')
        self.assertTrue(result['success'])
        self.assertEqual(result['issues_new'], 0)

    @patch('app.requests')
    def test_sync_issues_api_error(self, mock_requests):
        mock_requests.get.side_effect = Exception('Connection timeout')
        result = self.svc.sync_repository_issues('test/repo')
        self.assertFalse(result['success'])
        self.assertIn('Connection timeout', result['error'])

    @patch('app.requests', None)
    def test_sync_issues_no_requests_module(self):
        result = self.svc.sync_repository_issues('test/repo')
        self.assertFalse(result['success'])
        self.assertIn('requests module not available', result['error'])


class TestSyncPRs(TestServiceBase):
    """Test sync_repository_prs with mocked GitHub API responses."""

    @patch('app.requests')
    def test_sync_prs_success(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                'number': 42, 'title': 'Add feature', 'html_url': 'https://github.com/test/repo/pull/42',
                'created_at': '2024-01-01T00:00:00Z', 'updated_at': '2024-06-01T00:00:00Z',
                'state': 'open', 'body': 'New feature', 'labels': [],
                'assignees': [], 'assignee': None, 'comments': 0,
                'draft': False, 'merged': False,
                'base': {'ref': 'main'}, 'head': {'ref': 'feature-branch'},
                'user': {'login': 'dev', 'avatar_url': 'https://example.com/a.png'},
            }
        ]
        mock_requests.get.return_value = mock_response

        result = self.svc.sync_repository_prs('test/repo')
        self.assertTrue(result['success'])
        self.assertEqual(result['prs_new'], 1)

    @patch('app.requests')
    def test_sync_prs_304_not_modified(self, mock_requests):
        self.svc._update_sync_metadata(
            repository='test/repo', sync_type='pull_requests', status='success',
            items_synced=0, last_synced_at='2024-01-01T00:00:00Z',
        )
        mock_response = MagicMock()
        mock_response.status_code = 304
        mock_requests.get.return_value = mock_response

        result = self.svc.sync_repository_prs('test/repo')
        self.assertTrue(result['success'])
        self.assertEqual(result['prs_synced'], 0)

    @patch('app.requests')
    def test_sync_prs_api_error(self, mock_requests):
        mock_requests.get.side_effect = Exception('Network error')
        result = self.svc.sync_repository_prs('test/repo')
        self.assertFalse(result['success'])
        self.assertIn('Network error', result['error'])

    @patch('app.requests', None)
    def test_sync_prs_no_requests_module(self):
        result = self.svc.sync_repository_prs('test/repo')
        self.assertFalse(result['success'])


class TestValidateRepository(TestServiceBase):

    @patch('app.requests')
    def test_valid_repo(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'full_name': 'owner/repo', 'language': 'Python'}
        mock_requests.get.return_value = mock_response

        valid, metadata, error = self.svc._validate_repository_on_github('owner/repo')
        self.assertTrue(valid)
        self.assertEqual(metadata['full_name'], 'owner/repo')
        self.assertIsNone(error)

    @patch('app.requests')
    def test_repo_not_found(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests.get.return_value = mock_response

        valid, metadata, error = self.svc._validate_repository_on_github('owner/missing')
        self.assertFalse(valid)
        self.assertIn('not found', error)

    @patch('app.requests')
    def test_rate_limited(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_requests.get.return_value = mock_response

        valid, _, error = self.svc._validate_repository_on_github('owner/repo')
        self.assertFalse(valid)
        self.assertIn('rate limit', error)

    @patch('app.requests', None)
    def test_no_requests_module_skips_validation(self):
        valid, metadata, error = self.svc._validate_repository_on_github('owner/repo')
        self.assertTrue(valid)  # assumed valid when requests is unavailable


class TestAddRepository(TestServiceBase):

    @patch.object(GitHubSyncService, '_validate_repository_on_github',
                  return_value=(True, {'full_name': 'test/new-repo', 'language': 'Rust',
                                       'owner': {'login': 'test'}}, None))
    def test_add_success(self, _mock):
        result = self.svc.add_repository(
            repo='test/new-repo', display_name='New Repo',
            main_category='Test', classification='Rust', priority=1,
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['repository']['repo'], 'test/new-repo')

    @patch.object(GitHubSyncService, '_validate_repository_on_github',
                  return_value=(True, {'full_name': 'test/dup', 'language': 'Go',
                                       'owner': {'login': 'test'}}, None))
    def test_add_duplicate(self, _mock):
        self.svc.add_repository(repo='test/dup', display_name='Dup',
                                main_category='T', classification='Go', priority=1)
        result = self.svc.add_repository(repo='test/dup', display_name='Dup',
                                         main_category='T', classification='Go', priority=1)
        self.assertFalse(result['success'])
        self.assertIn('already exists', result['error'])

    @patch.object(GitHubSyncService, '_validate_repository_on_github',
                  return_value=(False, None, 'Not found on GitHub'))
    def test_add_invalid_repo(self, _mock):
        result = self.svc.add_repository(repo='bad/repo', display_name='Bad',
                                         main_category='T', classification='X', priority=1)
        self.assertFalse(result['success'])

    def test_add_invalid_format(self):
        result = self.svc.add_repository(repo='noslash', display_name='X',
                                         main_category='T', classification='X', priority=1)
        self.assertFalse(result['success'])


class TestGetRepositories(TestServiceBase):

    def test_empty_active(self):
        # Fresh DB has seeded repos — just verify the call works
        repos = self.svc.get_repositories()
        self.assertIsInstance(repos, list)

    def test_include_inactive(self):
        repos = self.svc.get_repositories(include_inactive=True)
        self.assertIsInstance(repos, list)

    def test_include_filters(self):
        repos = self.svc.get_repositories(include_filters=True)
        for r in repos:
            self.assertIn('filters', r)


# ---------------------------------------------------------------------------
# Static UI serving
# ---------------------------------------------------------------------------
class TestStaticUI(TestBase):

    def test_index_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!DOCTYPE html>', response.data)

    def test_management_page(self):
        response = self.client.get('/management')
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()