"""Separate public-source connectivity controls; never counted as exact-case successes."""
import json
from pathlib import Path

from experiments.video_search.alternatives import PROVIDERS
from experiments.video_search.providers import ProviderBlocked, safe_error
from experiments.video_search.run import download


def main():
    output = Path('video-search-output/source-controls').resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for source, query in [('commons', 'Emu War'), ('peertube', 'Emu War'), ('nasa', 'Apollo')]:
        result = dict(source=source, query=query, purpose='connectivity/decoder control; not benchmark ground truth', attempts=[])
        try:
            candidates = PROVIDERS[source](query, 5)
            for item in candidates[:3]:
                row = dict(item)
                try:
                    row.update(download(item, output, 'clip', 15, transcript_mode='off'))
                except Exception as error:
                    row.update(status='failed', error=safe_error(error))
                result['attempts'].append(row)
                if row['status'] == 'downloaded':
                    break
        except Exception as error:
            result['error'] = safe_error(error)
        results.append(result)
        (output/'controls.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
        print(source, [(r['status'], r.get('error', '')) for r in result['attempts']], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
