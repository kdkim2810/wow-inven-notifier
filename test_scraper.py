import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

import requests
import scraper as s


def listing(*ids):
    return '<table class="board-list"><tbody>' + ''.join(
        f'<tr><td class="num">{i}</td><td><a class="subject-link" href="/board/wow/2972/{i}">글 {i}</a></td></tr>'
        for i in ids) + '</tbody></table>'


class ScraperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.directory.name)
        Path(s.LAST_ID_FILE).write_text('100')
        Path(s.FAIL_COUNT_FILE).write_text('0')
        self.webhook = patch.object(s, 'WEBHOOK_URL', 'https://example.invalid/webhook')
        self.webhook.start()

    def tearDown(self):
        self.webhook.stop()
        os.chdir(self.cwd)
        self.directory.cleanup()

    def test_parse_orders_deduplicates_and_excludes_notice(self):
        html = listing(102, 101, 102).replace('</tbody>', '<tr><td class="num">공지</td><td><a class="subject-link" href="/board/wow/2972/9999">공지</a></td></tr></tbody>')
        self.assertEqual([p['id'] for p in s.parse_posts(html)], [101, 102])

    def test_empty_or_block_page_fails(self):
        for html in ['<html>점검 중</html>', '<table class="board-list"><tbody></tbody></table>']:
            with self.assertRaises(RuntimeError):
                s.parse_posts(html)

    def test_backlog_fetches_more_than_one_page(self):
        with patch.object(s, 'fetch_with_retry', side_effect=[SimpleNamespace(text=listing(104, 103)), SimpleNamespace(text=listing(102, 101, 100))]) as fetch:
            self.assertEqual([p['id'] for p in s.collect_new_posts(100)], [101, 102, 103, 104])
            self.assertEqual(fetch.call_count, 2)

    def test_repeated_page_fails_without_advancing(self):
        with patch.object(s, 'fetch_with_retry', return_value=SimpleNamespace(text=listing(104, 103))):
            with self.assertRaises(RuntimeError):
                s.collect_new_posts(100)
        self.assertEqual(s.read_counter(s.LAST_ID_FILE), 100)

    def test_first_run_uses_highest_id(self):
        with patch.object(s, 'fetch_with_retry', return_value=SimpleNamespace(text=listing(104, 102, 103))):
            self.assertEqual([p['id'] for p in s.collect_new_posts(0)], [104])

    def test_delivery_failure_retries_unsent_posts_next_run(self):
        posts = [{'id': i, 'title': str(i), 'link': 'link'} for i in [101, 102, 103]]
        with patch.object(s, 'collect_new_posts', return_value=posts), patch.object(s, 'send_discord_msg', side_effect=[None, RuntimeError('HTTP 500')]):
            self.assertEqual(s.main(), 1)
        self.assertEqual(s.read_counter(s.LAST_ID_FILE), 101)
        self.assertEqual(s.read_counter(s.FAIL_COUNT_FILE), 1)
        with patch.object(s, 'collect_new_posts', return_value=posts[1:]) as collect, patch.object(s, 'send_discord_msg') as send:
            self.assertEqual(s.main(), 0)
            collect.assert_called_once_with(101)
            self.assertEqual(send.call_count, 2)
        self.assertEqual(s.read_counter(s.LAST_ID_FILE), 103)
        self.assertEqual(s.read_counter(s.FAIL_COUNT_FILE), 0)

    def test_failure_email_only_at_threshold(self):
        with patch.object(s, 'collect_new_posts', side_effect=RuntimeError('인벤 접속 실패')), patch.object(s, 'send_fail_email') as email:
            for _ in range(5):
                self.assertEqual(s.main(), 1)
            self.assertEqual(email.call_count, 1)
            self.assertEqual(email.call_args.args[0], 3)
        self.assertEqual(s.read_counter(s.LAST_ID_FILE), 100)

    def test_dry_run_does_not_send_or_write(self):
        with patch.object(s, 'collect_new_posts', return_value=[{'id': 101}]), patch.object(s, 'send_discord_msg') as send:
            self.assertEqual(s.main(dry_run=True), 0)
            send.assert_not_called()
        self.assertEqual(s.read_counter(s.LAST_ID_FILE), 100)
        self.assertEqual(s.read_counter(s.FAIL_COUNT_FILE), 0)

    def test_webhook_failure_is_not_success(self):
        with patch.object(s.requests, 'post', return_value=SimpleNamespace(status_code=403)):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
                s.send_discord_msg('title', 'link')

    def test_webhook_rate_limit_retries(self):
        limited = Mock(status_code=429)
        limited.json.return_value = {'retry_after': 1}
        with patch.object(s.requests, 'post', side_effect=[limited, SimpleNamespace(status_code=204)]) as send, patch.object(s.time, 'sleep'):
            s.send_discord_msg('title', 'link')
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args.kwargs['json']['allowed_mentions'], {'parse': []})

    def test_network_exception_does_not_expose_webhook(self):
        with patch.object(s.requests, 'post', side_effect=requests.ConnectionError('secret-url')):
            with self.assertRaises(RuntimeError) as result:
                s.send_discord_msg('title', 'link')
        self.assertNotIn('secret-url', str(result.exception))

    def test_fetch_retries_and_signals_exhaustion(self):
        with patch.object(s.requests, 'get', side_effect=requests.ConnectionError('reset')) as get, patch.object(s.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                s.fetch_with_retry(s.BOARD_URL)
            self.assertEqual(get.call_count, 3)


    def test_non_finite_rate_limit_uses_safe_delay(self):
        limited = Mock(status_code=429)
        limited.json.return_value = {'retry_after': float('nan')}
        with patch.object(s.requests, 'post', side_effect=[limited, SimpleNamespace(status_code=204)]), patch.object(s.time, 'sleep') as sleep:
            s.send_discord_msg('title', 'link')
            sleep.assert_called_once_with(5)

    def test_long_rate_limit_preserves_checkpoint(self):
        limited = Mock(status_code=429)
        limited.json.return_value = {'retry_after': 120}
        with patch.object(s.requests, 'post', return_value=limited) as post, patch.object(s.time, 'sleep') as sleep:
            with self.assertRaises(RuntimeError):
                s.send_discord_msg('title', 'link')
            self.assertEqual(post.call_count, 1)
            sleep.assert_not_called()
        self.assertEqual(s.read_counter(s.LAST_ID_FILE), 100)

    def test_missing_checkpoint_stops_before_fetch(self):
        Path(s.LAST_ID_FILE).unlink()
        with patch.object(s, 'collect_new_posts') as collect:
            self.assertEqual(s.main(), 1)
            collect.assert_not_called()

    def test_broken_failure_counter_does_not_crash_error_handler(self):
        Path(s.FAIL_COUNT_FILE).write_text('broken')
        with patch.object(s, 'collect_new_posts', side_effect=RuntimeError('failure')):
            self.assertEqual(s.main(), 1)
        self.assertEqual(Path(s.FAIL_COUNT_FILE).read_text(), 'broken')

    def test_webhook_redirect_is_rejected(self):
        with patch.object(s.requests, 'post', return_value=SimpleNamespace(status_code=302)) as post:
            with self.assertRaises(RuntimeError):
                s.send_discord_msg('title', 'link')
            self.assertFalse(post.call_args.kwargs['allow_redirects'])

if __name__ == '__main__':
    unittest.main()
