from __future__ import annotations

import unittest

from ccet_crawler.models.hobby_job_summary import PayDetail


class PayDetailTimeBlocksNeededTest(unittest.TestCase):
    def test_exact_multiple(self) -> None:
        pay = PayDetail(job_track="Wizard", money_per_second=2_016_492, money_per_time_block_per_second=201_649)
        self.assertEqual(pay.time_blocks_needed(403_298), 2)
    # end def

    def test_rounds_up_remainder(self) -> None:
        pay = PayDetail(job_track="Wizard", money_per_second=2_016_492, money_per_time_block_per_second=201_649)
        self.assertEqual(pay.time_blocks_needed(500_000), 3)
    # end def

    def test_zero_rate_returns_zero(self) -> None:
        pay = PayDetail(job_track="Grave Digger", money_per_second=0, money_per_time_block_per_second=0)
        self.assertEqual(pay.time_blocks_needed(100), 0)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
