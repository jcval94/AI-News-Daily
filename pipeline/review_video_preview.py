from __future__ import annotations

PREVIEW_MARKER = 'data-lazy-video-preview="v1"'

LAZY_VIDEO_PREVIEW_SCRIPT = r"""
<script data-lazy-video-preview="v1">
(() => {
  const videos = Array.from(document.querySelectorAll('.media-card video'));
  if (!videos.length) return;

  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const saveData = Boolean(connection && connection.saveData);
  const queue = [];
  let active = 0;
  const MAX_CONCURRENT_PREVIEWS = 2;

  function finish(video) {
    if (video.dataset.previewInflight !== '1') return;
    video.dataset.previewInflight = '0';
    active = Math.max(0, active - 1);
    drain();
  }

  function warm(video) {
    if (video.dataset.previewWarm === '1') {
      finish(video);
      return;
    }
    video.dataset.previewWarm = '1';
    video.dataset.previewState = 'loading';
    video.preload = 'metadata';

    let timeoutId = window.setTimeout(() => {
      video.dataset.previewState = 'timeout';
      finish(video);
    }, 6000);

    const done = state => {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
        timeoutId = 0;
      }
      video.dataset.previewState = state;
      finish(video);
    };

    video.addEventListener('error', () => done('error'), {once:true});
    video.addEventListener('loadedmetadata', () => {
      const duration = Number(video.duration);
      if (!Number.isFinite(duration) || duration <= 0.12) {
        done('metadata');
        return;
      }
      const target = Math.min(0.45, Math.max(0.08, duration * 0.06));
      video.addEventListener('seeked', () => {
        video.pause();
        video.dataset.previewReady = '1';
        done('ready');
      }, {once:true});
      try {
        video.currentTime = target;
      } catch (_) {
        done('metadata');
      }
    }, {once:true});

    video.load();
  }

  function drain() {
    while (active < MAX_CONCURRENT_PREVIEWS && queue.length) {
      const video = queue.shift();
      if (!video || video.dataset.previewWarm === '1') continue;
      video.dataset.previewInflight = '1';
      active += 1;
      warm(video);
    }
  }

  function enqueue(video) {
    if (!video || video.dataset.previewQueued === '1' || video.dataset.previewWarm === '1') return;
    video.dataset.previewQueued = '1';
    queue.push(video);
    drain();
  }

  videos.forEach(video => {
    video.preload = 'none';

    video.addEventListener('pointerenter', () => enqueue(video), {once:true, passive:true});
    video.addEventListener('focus', () => enqueue(video), {once:true});
    video.addEventListener('touchstart', () => enqueue(video), {once:true, passive:true});
    video.addEventListener('play', () => {
      if (video.dataset.previewReady === '1' && video.currentTime < 0.6) {
        video.dataset.previewReady = '0';
        try { video.currentTime = 0; } catch (_) {}
      }
    }, {once:true});
  });

  if (!saveData && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        enqueue(entry.target);
      });
    }, {rootMargin:'80px 0px', threshold:0.01});
    videos.forEach(video => observer.observe(video));
  }
})();
</script>
"""


def upgrade_lazy_video_previews(document: str) -> str:
    """Load only enough bytes for a representative frame when a media video becomes visible.

    The initial page keeps every video at preload=none. The browser performs at most two
    concurrent metadata/range requests after the Media panel is actually visible, so the
    overview and other tabs pay effectively no video cost.
    """
    if "<video" not in document or PREVIEW_MARKER in document:
        return document
    document = document.replace("preload='metadata'", "preload='none'")
    document = document.replace('preload="metadata"', 'preload="none"')
    if "</body>" not in document:
        return document
    return document.replace("</body>", LAZY_VIDEO_PREVIEW_SCRIPT + "\n</body>", 1)
