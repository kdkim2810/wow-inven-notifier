import unittest
from types import SimpleNamespace
from unittest.mock import patch

import scraper


class DiscordTitleTests(unittest.TestCase):
    def test_brackets_are_escaped_in_link_label(self):
        with patch.object(scraper, 'WEBHOOK_URL', 'https://example.invalid'), patch.object(
            scraper.requests, 'post', return_value=SimpleNamespace(status_code=204)
        ) as post:
            scraper.send_discord_msg('[신화] 파티', 'https://www.inven.co.kr/board/wow/2972/123')
        expected = '[' + chr(92) + '[신화' + chr(92) + '] 파티](https://www.inven.co.kr/board/wow/2972/123)'
        self.assertIn(expected, post.call_args.kwargs['json']['content'])


if __name__ == '__main__':
    unittest.main()
