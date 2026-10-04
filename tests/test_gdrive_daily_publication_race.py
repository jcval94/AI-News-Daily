"""Run the deployed publication shell against local bare Git remotes only."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

import yaml

from tests.test_gdrive_news_bridge import digest, envelope


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "requires Git and Bash")
class PublicationRaceTests(unittest.TestCase):
    def exercise(self, mode):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.load((root/".github/workflows/gdrive-raw-bridge-probe.yml").read_text(), Loader=yaml.BaseLoader)
        script = next(s["run"] for s in workflow["jobs"]["consume"]["steps"] if s.get("id") == "publish")
        day = datetime.now(ZoneInfo("America/Mexico_City")).date().isoformat()
        target = f"news/{day}-18-45-00.txt"
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            seed, remote, worker, rival = [base/n for n in ("seed", "remote.git", "worker", "rival")]
            seed.mkdir()
            def git(*args, cwd=seed):
                return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
            git("init", "-b", "main")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (seed/"README.md").write_text("seed\n")
            git("add", "README.md")
            git("commit", "-m", "seed")
            git("clone", "--bare", str(seed), str(remote))
            git("clone", str(remote), str(worker))
            git("clone", str(remote), str(rival))
            git("config", "user.name", "Rival", cwd=rival)
            git("config", "user.email", "rival@example.invalid", cwd=rival)
            payload = digest(day + " 18:45:00").replace("Fecha: 2026-10-01", "Fecha: " + day)
            env_file = base/"envelope.txt"
            envelope(env_file, payload, target_path=target)
            env_file.write_text(env_file.read_text().replace("ai-news-daily.news.2026-10-01.184500", f"ai-news-daily.news.{day}.184500"))
            # Mimic the initial validator's untracked materialized candidate.
            (worker/"news").mkdir()
            (worker/target).write_text(payload + "\n")
            rival_digest = base/"rival-digest.txt"
            rival_digest.write_text(digest(day + " 18:40:00").replace("Fecha: 2026-10-01", "Fecha: " + day) + "\n")
            wrapper = '''
python() { "$PYTHON_BIN" "$@"; }
git() {
  if [ "$1" = "push" ] && [ "$RACE_MODE" != "none" ] && [ ! -f "$RACE_MARKER" ]; then
    touch "$RACE_MARKER"
    if [ "$RACE_MODE" = "digest" ]; then
      mkdir -p "$RIVAL/news"
      cp "$RIVAL_DIGEST" "$RIVAL/news/$DIGEST_DATE-18-40-00.txt"
      command git -C "$RIVAL" add news
    else
      printf 'concurrent lane\\n' > "$RIVAL/concurrent.txt"
      command git -C "$RIVAL" add concurrent.txt
    fi
    command git -C "$RIVAL" commit -m "concurrent publication"
    command git -C "$RIVAL" push origin HEAD:main
  fi
  command git "$@"
}
'''
            environment = {**os.environ, "PYTHONPATH": str(root), "PYTHON_BIN": sys.executable,
                "GITHUB_REPOSITORY": "jcval94/AI-News-Daily", "GITHUB_OUTPUT": str(base/"outputs"),
                "RUNNER_TEMP": str(base), "DIGEST_PATH": target, "DIGEST_DATE": day,
                "TEST_ENVELOPE": str(env_file), "RACE_MODE": mode, "RACE_MARKER": str(base/"race"),
                "RIVAL": str(rival), "RIVAL_DIGEST": str(rival_digest)}
            run = subprocess.run(["bash", "-c", wrapper + script.replace("/tmp/ai-news-envelope.txt", '"$TEST_ENVELOPE"')], cwd=worker, env=environment, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            output = dict(l.split("=", 1) for l in (base/"outputs").read_text().splitlines())
            tree = git("--git-dir", str(remote), "ls-tree", "-r", "--name-only", "main").stdout.splitlines()
            news = [p for p in tree if p.startswith("news/")]
            self.assertEqual(len(news), 1)
            if mode == "digest":
                self.assertEqual(output["status"], "race_existing")
                self.assertNotIn(target, tree)
            else:
                self.assertEqual(output["status"], "published")
                self.assertIn(target, tree)
                changed = git("--git-dir", str(remote), "diff-tree", "--no-commit-id", "--name-only", "-r", "main").stdout.splitlines()
                self.assertEqual(changed, [target])
                if mode == "unrelated":
                    self.assertIn("concurrent.txt", tree)

    def test_initial_materialized_candidate_does_not_fake_already_exists(self):
        self.exercise("none")

    def test_unrelated_main_race_is_retried_without_losing_other_lane(self):
        self.exercise("unrelated")

    def test_same_day_competing_digest_prevents_duplicate_publication(self):
        self.exercise("digest")


if __name__ == "__main__":
    unittest.main()
