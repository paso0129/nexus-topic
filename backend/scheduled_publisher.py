#!/usr/bin/env python3
"""
Scheduled Article Publisher

Automatically generates and publishes articles at scheduled intervals.
"""

import schedule
import time
import subprocess
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Configure logging
log_file = f'scheduled_publisher_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ScheduledPublisher:
    def __init__(self, total_hours=15, articles_per_run=1):
        """
        Initialize scheduled publisher.

        Args:
            total_hours: Total hours to run (default: 15)
            articles_per_run: Number of articles to generate per run (default: 1)
        """
        self.total_hours = total_hours
        self.articles_per_run = articles_per_run
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=total_hours)
        self.articles_generated = 0
        self.successful_runs = 0
        self.failed_runs = 0

    def should_continue(self):
        """Check if we should continue running."""
        current_time = datetime.now()
        if current_time >= self.end_time:
            logger.info(f"Reached end time ({self.end_time}). Stopping scheduler.")
            return False
        return True

    def generate_article(self):
        """Generate and publish one article."""
        if not self.should_continue():
            return schedule.CancelJob

        logger.info("=" * 80)
        logger.info(f"Starting scheduled article generation #{self.successful_runs + 1}")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Articles generated so far: {self.articles_generated}")
        logger.info("=" * 80)

        try:
            # Run main.py to generate article
            result = subprocess.run(
                ['python3', 'main.py', '--articles', str(self.articles_per_run), '--no-adsense'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode == 0:
                self.successful_runs += 1
                self.articles_generated += self.articles_per_run
                logger.info(f"✓ Successfully generated {self.articles_per_run} article(s)")
                logger.info(f"Total articles: {self.articles_generated}/{self.total_hours}")
            else:
                self.failed_runs += 1
                logger.error(f"✗ Failed to generate article. Exit code: {result.returncode}")
                logger.error(f"Error output: {result.stderr[:500]}")

        except subprocess.TimeoutExpired:
            self.failed_runs += 1
            logger.error("✗ Article generation timed out (10 minutes)")
        except Exception as e:
            self.failed_runs += 1
            logger.error(f"✗ Error generating article: {str(e)}")

        # Print statistics
        remaining_hours = (self.end_time - datetime.now()).total_seconds() / 3600
        logger.info(f"\nStatistics:")
        logger.info(f"  Successful: {self.successful_runs}")
        logger.info(f"  Failed: {self.failed_runs}")
        logger.info(f"  Total articles: {self.articles_generated}")
        logger.info(f"  Time remaining: {remaining_hours:.1f} hours")
        logger.info(f"  Next run: {(datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80 + "\n")

        # Check if we should cancel the job
        if not self.should_continue():
            logger.info("Scheduler finished. Final statistics:")
            logger.info(f"  Total articles generated: {self.articles_generated}")
            logger.info(f"  Successful runs: {self.successful_runs}")
            logger.info(f"  Failed runs: {self.failed_runs}")
            logger.info(f"  Duration: {total_hours} hours")
            return schedule.CancelJob


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Scheduled article publisher - generates articles at regular intervals',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 1 article every hour for 15 hours
  python3 scheduled_publisher.py --hours 15 --articles 1

  # Generate 2 articles every hour for 10 hours
  python3 scheduled_publisher.py --hours 10 --articles 2

  # Run in background
  nohup python3 scheduled_publisher.py --hours 15 &
        """
    )

    parser.add_argument(
        '--hours',
        type=int,
        default=15,
        help='Total hours to run (default: 15)'
    )

    parser.add_argument(
        '--articles',
        type=int,
        default=1,
        help='Articles to generate per hour (default: 1)'
    )

    parser.add_argument(
        '--immediate',
        action='store_true',
        help='Generate first article immediately (default: wait 1 hour)'
    )

    args = parser.parse_args()

    logger.info("╔" + "═" * 78 + "╗")
    logger.info("║" + " " * 20 + "SCHEDULED ARTICLE PUBLISHER" + " " * 31 + "║")
    logger.info("╚" + "═" * 78 + "╝")
    logger.info(f"\nConfiguration:")
    logger.info(f"  Duration: {args.hours} hours")
    logger.info(f"  Articles per hour: {args.articles}")
    logger.info(f"  Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  End time: {(datetime.now() + timedelta(hours=args.hours)).strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Log file: {log_file}")
    logger.info(f"  Immediate start: {args.immediate}")
    logger.info("")

    # Create publisher
    publisher = ScheduledPublisher(total_hours=args.hours, articles_per_run=args.articles)

    # Schedule job to run every hour
    schedule.every().hour.do(publisher.generate_article)

    # Run immediately if requested
    if args.immediate:
        logger.info("Running first article generation immediately...\n")
        publisher.generate_article()

    logger.info("Scheduler started. Press Ctrl+C to stop.\n")

    try:
        while publisher.should_continue():
            schedule.run_pending()
            time.sleep(60)  # Check every minute

        logger.info("\n✓ Scheduler completed successfully!")

    except KeyboardInterrupt:
        logger.info("\n\nScheduler stopped by user.")
        logger.info(f"Articles generated: {publisher.articles_generated}")
        logger.info(f"Successful runs: {publisher.successful_runs}")
        logger.info(f"Failed runs: {publisher.failed_runs}")
    except Exception as e:
        logger.error(f"\n\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
