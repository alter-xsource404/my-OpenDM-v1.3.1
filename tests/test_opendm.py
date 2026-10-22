"""Run with:  python -m unittest discover -s tests -v   (no network needed; uses local servers)"""
import hashlib, http.server, json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, unittest
import urllib.error, urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import opendm

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    HAVE_AES = True
except ImportError:
    HAVE_AES = False

BIG = os.urandom(3 * 1024 * 1024)
HLS, SEGS, SEEN, PORT = {}, {}, {}, {}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", extra=None):
        self.send_response(code)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        SEEN[(self.server.server_address[1], self.path)] = dict(self.headers)
        if self.path == "/site/index.html":
            page = (b'<html><head><title>My  Photos</title></head><body><a href="/site/a.jpg">a</a><img src="b.png"><a href="doc.pdf">d</a>'
                    b'<a href="more.html">more</a><a href="https://elsewhere.example/page.html">x</a><link href="style.css"><a href="mailto:x@y.z">m</a></body></html>')
            return self._send(200, page, {"Content-Type": "text/html; charset=utf-8"})
        if self.path == "/site/more.html":
            return self._send(200, b'<a href="deep.zip">z</a><a href="a.jpg">dup</a>', {"Content-Type": "text/html"})
        if self.path == "/cd":  # the real name only shows up in a header
            return self._send(200, os.urandom(3000), {"Content-Disposition": 'attachment; filename="photo.JPG"'})
        if self.path == "/r":  # redirect to a *different* host:port
            return self._send(302, extra={"Location": f"http://127.0.0.1:{PORT['b']}/landing"})
        body = {"/landing": b"ok", "/file.bin": BIG}.get(self.path) or HLS.get(self.path)
        if body is None:
            return self._send(404)
        rng = self.headers.get("Range")
        if rng:
            a, b = re.match(r"bytes=(\d+)-(\d*)", rng).groups()
            a, b = int(a), int(b) if b else len(body) - 1
            return self._send(206, body[a:b + 1], {"Content-Range": f"bytes {a}-{b}/{len(body)}"})
        self._send(200, body)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_tracks():
    """Real silent-video + audio-only files, like Facebook/Instagram serve them (needs ffmpeg; else those tests skip)."""
    if not shutil.which("ffmpeg"):
        return
    d = tempfile.mkdtemp()
    try:
        ff = ["ffmpeg", "-y", "-loglevel", "error"]
        subprocess.run(ff + ["-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25", "-an", "-c:v", "libx264",
                             "-preset", "ultrafast", "-movflags", "+faststart", d + "/v.mp4"], check=True, capture_output=True)
        subprocess.run(ff + ["-f", "lavfi", "-i", "sine=duration=3", "-vn", "-c:a", "aac", d + "/a.m4a"], check=True, capture_output=True)
        for url, name in (("/mux/video.mp4", "/v.mp4"), ("/mux/audio.m4a", "/a.m4a")):
            with open(d + name, "rb") as f:
                HLS[url] = f.read()
    except (subprocess.CalledProcessError, OSError):
        pass
    finally:
        shutil.rmtree(d, ignore_errors=True)


def setUpModule():
    HLS["/mux/fv.mp4"], HLS["/mux/fa.m4a"] = os.urandom(300_000), os.urandom(80_000)  # stand-ins when ffmpeg is absent
    for n in ("clip.mp4", "report.pdf", "data.zip", "song.mp3", "setup.exe", "notes.xyz"):
        HLS["/files/" + n] = os.urandom(5000)
    _make_tracks()
    for name in ("a", "b"):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        PORT[name] = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    for q in ("hi", "lo", "enc"):
        SEGS[q] = [os.urandom(20000 + 1000 * i) for i in range(5)]
    for q in ("hi", "lo"):
        pl = ["#EXTM3U", "#EXT-X-TARGETDURATION:2"]
        for i, s in enumerate(SEGS[q]):
            HLS[f"/hls/{q}{i}.ts"] = s
            pl += ["#EXTINF:2,", f"{q}{i}.ts"]
        HLS[f"/hls/{q}.m3u8"] = "\n".join(pl + ["#EXT-X-ENDLIST"]).encode()
    HLS["/hls/master.m3u8"] = (b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=640x360\nhi.m3u8\n"
                               b"#EXT-X-STREAM-INF:BANDWIDTH=300,RESOLUTION=320x180\nlo.m3u8\n")
    HLS["/hls/live.m3u8"] = HLS["/hls/hi.m3u8"].replace(b"#EXT-X-ENDLIST", b"")
    HLS["/hls/drm.m3u8"] = b'#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="skd://x"\n#EXTINF:2,\nhi0.ts\n#EXT-X-ENDLIST\n'
    if HAVE_AES:
        key, pl = os.urandom(16), ["#EXTM3U", '#EXT-X-KEY:METHOD=AES-128,URI="key"']
        HLS["/hls/key"] = key
        for i, s in enumerate(SEGS["enc"]):  # no IV attribute: IV must be the segment sequence number
            p = padding.PKCS7(128).padder()
            e = Cipher(algorithms.AES(key), modes.CBC(i.to_bytes(16, "big"))).encryptor()
            HLS[f"/hls/enc{i}.ts"] = e.update(p.update(s) + p.finalize()) + e.finalize()
            pl += ["#EXTINF:2,", f"enc{i}.ts"]
        HLS["/hls/enc.m3u8"] = "\n".join(pl + ["#EXT-X-ENDLIST"]).encode()


def A(path):
    return f"http://127.0.0.1:{PORT['a']}{path}"


def run(d, timeout=60):
    d.start()
    t = time.time()
    while d.status in ("Connecting", "Downloading", "Queued") and time.time() - t < timeout:
        time.sleep(0.02)
    return d


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        opendm.GLOBAL_LIMIT.set_rate(0)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestHttp(Base):
    def test_segmented_download_is_intact(self):
        d = run(opendm.Download(A("/file.bin"), self.tmp, 4))
        self.assertEqual(d.status, "Completed")
        self.assertEqual(md5(d.path), hashlib.md5(BIG).hexdigest())
        self.assertGreaterEqual(len(d.segs), 4)

    def test_pause_and_resume_from_saved_state(self):
        opendm.GLOBAL_LIMIT.set_rate(1 << 20)
        d = opendm.Download(A("/file.bin"), self.tmp, 4)
        d.start()
        time.sleep(0.8)
        d.pause()
        d.thread.join()
        self.assertEqual(d.status, "Paused")
        self.assertTrue(0 < d.percent < 100)
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))  # survives a restart
        opendm.GLOBAL_LIMIT.set_rate(0)
        run(d2)
        self.assertEqual(d2.status, "Completed")
        self.assertEqual(md5(d2.path), hashlib.md5(BIG).hexdigest())

    def test_speed_limit(self):
        opendm.GLOBAL_LIMIT.set_rate(1 << 20)  # 3 MB at 1 MB/s
        t = time.time()
        d = run(opendm.Download(A("/file.bin"), self.tmp, 4))
        self.assertEqual(d.status, "Completed")
        self.assertGreater(time.time() - t, 2.3)

    def test_work_stealing_splits_largest_segment(self):
        d = opendm.Download("http://x.test/f", self.tmp)
        d.ranges, d.segs = True, [[0, 9_999_999, 1_000_000], [10_000_000, 10_000_100, 10_000_000]]
        new = d._steal()
        self.assertEqual(new[1], 9_999_999)
        self.assertEqual(d.segs[0][1], new[0] - 1)
        self.assertTrue(4_000_000 < new[0] < 7_000_000)
        d.segs = [[0, 500_000, 0]]
        self.assertIsNone(d._steal())  # too small to be worth splitting

    def test_cookie_is_not_forwarded_to_another_host(self):
        run(opendm.Download(A("/r"), self.tmp, 1, cookie="session=SECRET"))
        self.assertIn("Cookie", SEEN[(PORT["a"], "/r")])
        self.assertNotIn("Cookie", SEEN[(PORT["b"], "/landing")])


class TestScheduler(Base):
    def test_window(self):
        m = opendm.Manager(persist=False)
        self.assertTrue(m.in_window(12 * 60))  # scheduler off
        m.settings.update(sched_on=True, start="01:00", stop="07:00")
        self.assertEqual([m.in_window(h * 60) for h in (0, 3, 8)], [False, True, False])
        m.settings.update(start="22:00", stop="06:00")  # overnight
        self.assertEqual([m.in_window(h * 60) for h in (12, 23, 3)], [False, True, True])

    def test_closed_window_blocks_queue_but_manual_start_overrides(self):
        m = opendm.Manager(persist=False)
        m.in_window = lambda now_min=None: False
        d = m.add("http://127.0.0.1:1/x", self.tmp)
        d.status = "Queued"
        m.schedule()
        self.assertEqual(d.status, "Queued")
        d.force = True
        m.schedule()
        self.assertNotEqual(d.status, "Queued")
        d.pause()


class TestApi(Base):
    def test_auth_rules(self):
        m, port = opendm.Manager(persist=False), free_port()
        srv = opendm.start_api(m, lambda: (self.tmp, 4), port=port)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        tok = opendm.get_token()

        def call(path, data=None, token=tok, origin="chrome-extension://abc", host=None):
            h = {"X-OpenDM-Token": token, "Content-Type": "application/json"}
            if origin:
                h["Origin"] = origin
            if host:
                h["Host"] = host
            r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=h,
                                       data=json.dumps(data).encode() if data else None)
            try:
                return urllib.request.urlopen(r, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code
        self.assertEqual(call("/ping"), 200)
        self.assertEqual(call("/ping", token="nope"), 401)
        self.assertEqual(call("/ping", origin="https://evil.example"), 403)
        self.assertEqual(call("/ping", host="evil.example:%d" % port), 403)
        self.assertEqual(call("/add", {"url": "file:///etc/passwd"}), 400)
        self.assertEqual(call("/add", {"url": "https://x.test/a.zip", "cookie": "s=1"}), 200)
        self.assertEqual(call("/add", {"url": "https://x.test/s?id=1", "kind": "hls"}), 200)
        self.assertEqual(call("/add", {"url": "https://x.test/m.m3u8", "kind": "hls", "quality": 720, "bandwidth": 900000}), 200)
        self.assertEqual(call("/add", {"url": "https://x.test/f.zip", "quality": 720}), 200)  # ignored for non-HLS
        self.assertEqual([type(d).__name__ for d in m.items], ["Download", "HlsDownload", "HlsDownload", "Download"])
        self.assertEqual((m.items[2].quality, m.items[2].pick_bw), (720, 900000))
        self.assertNotIn("cookie", m.items[0].to_dict())  # never written to disk


@mock.patch("opendm.shutil.which", return_value=None)  # deterministic: no ffmpeg remux
class TestHls(Base):
    def hls(self, path, **kw):
        return run(opendm.HlsDownload(A(path), self.tmp, 3, hint="clip", **kw))

    def content(self, d):
        with open(d.path, "rb") as f:
            return f.read()

    def test_master_picks_best_quality(self, _):
        d = self.hls("/hls/master.m3u8")
        self.assertEqual((d.status, d.name), ("Completed", "clip.ts"))
        self.assertEqual(self.content(d), b"".join(SEGS["hi"]))
        self.assertFalse(os.path.exists(d.path + ".parts"))

    def test_quality_cap(self, _):
        self.assertEqual(self.content(self.hls("/hls/master.m3u8", quality=200)), b"".join(SEGS["lo"]))

    @unittest.skipUnless(HAVE_AES, "pip install cryptography")
    def test_aes128_with_implicit_iv(self, _):
        d = self.hls("/hls/enc.m3u8")
        self.assertEqual(d.status, "Completed")
        self.assertEqual(self.content(d), b"".join(SEGS["enc"]))

    def test_exact_variant_pick_by_bitrate(self, _):
        # two 720p renditions with different bitrates: height alone can't tell them apart
        HLS["/hls/same.m3u8"] = (b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720\nhi.m3u8\n"
                                 b"#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=1280x720\nlo.m3u8\n")
        self.assertEqual(self.content(self.hls("/hls/same.m3u8")), b"".join(SEGS["hi"]))
        d = self.hls("/hls/same.m3u8", quality=720, pick_bw=900000)
        self.assertEqual(self.content(d), b"".join(SEGS["lo"]))

    def test_live_and_drm_are_rejected(self, _):
        live, drm = self.hls("/hls/live.m3u8"), self.hls("/hls/drm.m3u8")
        self.assertEqual((live.status, drm.status), ("Error", "Error"))
        self.assertIn("Live", live.error)
        self.assertIn("DRM", drm.error)



class TestMux(Base):
    """Video-only + audio-only downloads, merged into one playable mp4."""
    def mux(self, v="/mux/fv.mp4", a="/mux/fa.m4a", **kw):
        return run(opendm.MuxDownload(A(v), self.tmp, 2, audio_url=A(a), hint="My Clip 720p.mp4", **kw), timeout=90)

    def files(self):
        return sorted(os.listdir(self.tmp))

    @mock.patch("opendm.shutil.which", return_value=None)
    def test_without_ffmpeg_both_files_are_kept(self, _):
        d = self.mux()
        self.assertEqual(d.status, "Completed")
        self.assertEqual(self.files(), ["My Clip 720p (audio only).m4a", "My Clip 720p (video only).mp4"])
        with open(os.path.join(self.tmp, "My Clip 720p (video only).mp4"), "rb") as f:
            self.assertEqual(f.read(), HLS["/mux/fv.mp4"])
        self.assertIn("ffmpeg not found", d.note)

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_merge_produces_one_playable_file_with_picture_and_sound(self):
        if "/mux/video.mp4" not in HLS:
            self.skipTest("this ffmpeg can't encode test media")
        d = self.mux("/mux/video.mp4", "/mux/audio.m4a")
        self.assertEqual((d.status, d.note), ("Completed", ""))
        self.assertEqual(self.files(), ["My Clip 720p.mp4"])  # no temp folder left behind
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", d.path],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(out), ["audio", "video"])

    @mock.patch("opendm.shutil.which", return_value=None)
    def test_pause_resume_and_restart(self, _):
        opendm.GLOBAL_LIMIT.set_rate(100 * 1024)
        d = opendm.MuxDownload(A("/mux/fv.mp4"), self.tmp, 2, audio_url=A("/mux/fa.m4a"), hint="clip.mp4")
        d.start()
        time.sleep(1.2)
        d.pause()
        d.thread.join()
        self.assertEqual(d.status, "Paused")
        self.assertTrue(0 < d.percent < 100, d.percent)
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))  # survives an app restart
        self.assertIsInstance(d2, opendm.MuxDownload)
        self.assertEqual(len(d2.children), 2)
        opendm.GLOBAL_LIMIT.set_rate(0)
        run(d2)
        self.assertEqual(d2.status, "Completed")
        with open(os.path.join(self.tmp, "clip (video only).mp4"), "rb") as f:
            self.assertEqual(f.read(), HLS["/mux/fv.mp4"])

    def test_a_failing_part_is_reported(self):
        d = self.mux(a="/mux/missing.m4a")
        self.assertEqual(d.status, "Error")
        self.assertTrue(d.error)

    @mock.patch("opendm.shutil.which", return_value=None)
    def test_removing_a_paused_download_deletes_its_temp_files(self, _):
        opendm.GLOBAL_LIMIT.set_rate(50 * 1024)
        m = opendm.Manager(persist=False)
        d = m.add(A("/mux/fv.mp4"), self.tmp, 2, kind="mux", audio_url=A("/mux/fa.m4a"))
        d.start()
        time.sleep(1)
        m.remove(d, delete_file=True)
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith(".opendm-")], [])

    def test_hls_discard_removes_parts_folder(self):
        d = opendm.HlsDownload("http://x.test/a.m3u8", self.tmp)
        d.path = os.path.join(self.tmp, "x.ts")
        os.makedirs(d.path + ".parts")
        d.discard()
        self.assertFalse(os.path.exists(d.path + ".parts"))

    def test_api_audio_url_creates_a_merge_job(self):
        m, port = opendm.Manager(persist=False), free_port()
        srv = opendm.start_api(m, lambda: (self.tmp, 4), port=port)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def add(data):
            r = urllib.request.Request(f"http://127.0.0.1:{port}/add", data=json.dumps(data).encode(),
                                       headers={"X-OpenDM-Token": opendm.get_token(), "Content-Type": "application/json"})
            return urllib.request.urlopen(r, timeout=5).status
        add({"url": "https://x.test/v.mp4", "audioUrl": "https://x.test/a.m4a", "filename": "Clip 720p.mp4"})
        add({"url": "https://x.test/v.mp4", "audioUrl": "file:///etc/passwd"})  # not a web URL: ignored
        self.assertEqual([type(d).__name__ for d in m.items], ["MuxDownload", "Download"])
        self.assertEqual((m.items[0].audio_url, m.items[0].name), ("https://x.test/a.m4a", "Clip 720p.mp4"))
        for d in m.items:
            d.pause()


class TestCategories(Base):
    def mgr(self, **settings):
        m = opendm.Manager(persist=False)
        m.settings.update(folder=self.tmp, **settings)
        return m

    def finish(self, m, *downloads, timeout=60):
        t = time.time()
        while any(d.status not in ("Completed", "Error") for d in downloads) and time.time() - t < timeout:
            m.schedule()
            time.sleep(0.05)

    def rel(self, d):
        return os.path.relpath(d.path, self.tmp).replace(os.sep, "/")

    def test_classify_by_extension_site_and_default(self):
        cats = opendm.DEFAULT_CATEGORIES
        self.assertEqual([opendm.classify(cats, n) for n in ("a.MP4", "b.pdf", "c.tar.gz", "d.exe", "e.jpg", "f.mp3", "g.unknown", "noext")],
                         ["Video", "Documents", "Compressed", "Programs", "Images", "Music", "General", "General"])
        site = cats + [{"name": "Courses", "exts": [], "folder": "", "sites": ["school.example"]}]
        self.assertEqual(opendm.classify(site, "lesson.mp4", "https://cdn.school.example/x"), "Courses")  # a site rule beats the extension
        self.assertEqual(opendm.classify(site, "lesson.mp4", "https://notschool.example/x"), "Video")

    def test_category_folder_rules(self):
        cats = [{"name": "General", "exts": [], "folder": "", "sites": []}, {"name": "Video", "exts": ["mp4"], "folder": "", "sites": []},
                {"name": "Work", "exts": [], "folder": "Office/Docs", "sites": []}, {"name": "Abs", "exts": [], "folder": os.path.abspath("/abs/place"), "sites": []}]
        f = lambda n: opendm.category_folder(cats, n, "/base")
        self.assertEqual([f("General"), f("Video"), f("Work"), f("Abs"), f("Nope")],
                         ["/base", os.path.join("/base", "Video"), os.path.join("/base", "Office/Docs"), os.path.abspath("/abs/place"), "/base"])

    def test_downloads_land_in_their_category_folders(self):
        m = self.mgr()
        ds = [m.add(A("/files/" + n), self.tmp, 2) for n in ("clip.mp4", "report.pdf", "data.zip", "song.mp3", "setup.exe", "notes.xyz")]
        self.assertEqual([d.category for d in ds], ["Video", "Documents", "Compressed", "Music", "Programs", "General"])  # provisional, from the URL
        self.finish(m, *ds)
        self.assertEqual([d.status for d in ds], ["Completed"] * 6)
        self.assertEqual([self.rel(d) for d in ds], ["Video/clip.mp4", "Documents/report.pdf", "Compressed/data.zip", "Music/song.mp3", "Programs/setup.exe", "notes.xyz"])

    def test_real_name_from_content_disposition_decides_the_category(self):
        m = self.mgr()
        d = m.add(A("/cd"), self.tmp, 1)
        self.assertEqual(d.category, "General")  # the URL says nothing...
        self.finish(m, d)
        self.assertEqual((d.category, self.rel(d)), ("Images", "Images/photo.JPG"))  # ...the server's file name does

    def test_auto_sort_off_keeps_everything_in_the_base_folder(self):
        m = self.mgr(auto_sort=False)
        d = m.add(A("/files/clip.mp4"), self.tmp, 1)
        self.finish(m, d)
        self.assertEqual((d.category, self.rel(d)), ("Video", "clip.mp4"))  # still labelled, just not moved

    def test_user_choice_is_pinned_and_wins_over_the_extension(self):
        m = self.mgr()
        d = m.add(A("/files/data.zip"), self.tmp, 1)
        m.move_to_category(d, "Music")
        self.finish(m, d)
        self.assertEqual((d.category, d.auto_cat, self.rel(d)), ("Music", False, "Music/data.zip"))

    def test_moving_a_finished_file_and_refusing_a_partial_one(self):
        m = self.mgr()
        d = m.add(A("/files/report.pdf"), self.tmp, 1)
        self.finish(m, d)
        m.move_to_category(d, "Compressed")
        self.assertEqual(self.rel(d), "Compressed/report.pdf")
        self.assertTrue(os.path.exists(d.path) and not os.path.exists(os.path.join(self.tmp, "Documents", "report.pdf")))
        opendm.GLOBAL_LIMIT.set_rate(20 * 1024)
        slow = m.add(A("/file.bin"), self.tmp, 1)
        slow.start()
        time.sleep(0.8)
        slow.pause()
        slow.thread.join()
        with self.assertRaises(ValueError):
            m.move_to_category(slow, "Video")  # half a file on disk
        with self.assertRaises(ValueError):
            m.move_to_category(d, "No such category")

    def test_category_survives_a_restart(self):
        m = self.mgr()
        d = m.add(A("/files/clip.mp4"), self.tmp, 1)
        m.move_to_category(d, "Music")
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))
        self.assertEqual((d2.category, d2.auto_cat, d2.base, d2.folder), ("Music", False, d.base, d.folder))

    def test_custom_category_with_its_own_folder(self):
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, True)
        m = self.mgr(categories=opendm.DEFAULT_CATEGORIES + [{"name": "Tunes", "exts": ["mp3"], "folder": other, "sites": []}])
        m._fix_categories()
        d = m.add(A("/files/song.mp3"), self.tmp, 1)
        self.finish(m, d)
        self.assertEqual((d.category, os.path.dirname(d.path)), ("Music", os.path.join(self.tmp, "Music")))  # Music is listed first: first match wins
        m.settings["categories"] = [c for c in m.settings["categories"] if c["name"] != "Music"]
        d2 = m.add(A("/files/song.mp3"), self.tmp, 1)
        self.finish(m, d2)
        self.assertEqual((d2.category, os.path.dirname(d2.path)), ("Tunes", other))

    def test_hls_and_merged_videos_are_sorted_too(self):
        m = self.mgr()
        with mock.patch("opendm.shutil.which", return_value=None):
            h = m.add(A("/hls/hi.m3u8"), self.tmp, 2, hint="clip")
            x = m.add(A("/mux/fv.mp4"), self.tmp, 2, kind="mux", audio_url=A("/mux/fa.m4a"), hint="reel.mp4")
            self.finish(m, h, x, timeout=90)
        self.assertEqual([d.status for d in (h, x)], ["Completed", "Completed"])
        self.assertEqual(self.rel(h), "Video/clip.ts")
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, "Video"))), ["clip.ts", "reel (audio only).m4a", "reel (video only).mp4"])

    def test_bad_hand_edited_settings_are_repaired(self):
        m = self.mgr(categories=[{"name": "Video", "exts": [".MP4"]}, "junk", {"name": ""}, {"folder": "x"}])
        m._fix_categories()
        self.assertEqual([c["name"] for c in m.settings["categories"]], ["General", "Video"])
        self.assertEqual(m.settings["categories"][1]["exts"], ["mp4"])

    def test_filters_and_tooltip(self):
        m = self.mgr()
        a, b = m.add("http://x.test/a.mp4", self.tmp), m.add("http://x.test/b.pdf", self.tmp)
        a.status = "Completed"
        b.status = "Downloading"
        self.assertEqual([[opendm.matches_filter(d, f) for d in (a, b)] for f in ("all", "unfinished", "finished", "cat:Video", "cat:Documents")],
                         [[True, True], [False, True], [True, False], [True, False], [False, True]])
        self.assertEqual(opendm.tray_tooltip([a], 0), "OpenDM - idle")
        self.assertEqual(opendm.tray_tooltip([a, b], 2 * 1024 * 1024), "OpenDM - 1 downloading, 2.0 MB/s")


def _fake_pystray():
    """Stand-ins for pystray and Pillow so the tray menu logic is testable without a desktop."""
    import types
    py, pil, image = types.ModuleType("pystray"), types.ModuleType("PIL"), types.ModuleType("PIL.Image")

    class MenuItem:
        def __init__(self, text, action=None, checked=None, radio=False, default=False):
            self.text, self.action, self.checked, self.radio, self.default = text, action, checked, radio, default

    class Menu:
        SEPARATOR = "-"
        def __init__(self, *items):
            self.items = items

    class Icon:
        def __init__(self, name, image, title, menu):
            self.name, self.image, self.title, self.menu, self.running, self.notes = name, image, title, menu, False, []
        def run_detached(self): self.running = True
        def stop(self): self.running = False
        def notify(self, message, title): self.notes.append((title, message))
    py.MenuItem, py.Menu, py.Icon = MenuItem, Menu, Icon
    image.open = lambda fp: types.SimpleNamespace(load=lambda: None, size=(128, 128))
    pil.Image = image
    return {"pystray": py, "PIL": pil, "PIL.Image": image}


class TestTray(unittest.TestCase):
    def tray(self, limit=0):
        with mock.patch.dict(sys.modules, _fake_pystray()), mock.patch("opendm.platform.system", return_value="Linux"):
            return opendm.Tray(b"png", lambda: limit)

    def test_menu_has_the_expected_entries_and_clicks_are_queued(self):
        tr = self.tray(limit=512)
        self.assertTrue(tr.available)
        items = tr.icon.menu.items
        self.assertEqual([i if isinstance(i, str) else i.text for i in items],
                         ["Show OpenDM", "Pause all", "Resume all", "Speed limit", "Open download folder", "-", "Quit OpenDM"])
        self.assertTrue(items[0].default)  # double-clicking the icon shows the window
        for i in (items[0], items[1], items[2], items[4], items[6]):
            i.action(tr.icon, i)
        self.assertEqual(tr.poll(), ["show", "pause_all", "resume_all", "folder", "quit"])
        self.assertEqual(tr.poll(), [])
        sub = items[3].action.items
        self.assertEqual([i.text for i in sub], ["No limit", "256 KB/s", "512 KB/s", "1 MB/s", "5 MB/s"])
        self.assertEqual([i.checked(i) for i in sub], [False, False, True, False, False])  # the current limit is ticked
        sub[3].action()
        self.assertEqual(tr.poll(), ["limit:1024"])

    def test_title_notification_and_stop(self):
        tr = self.tray()
        tr.start()
        self.assertTrue(tr.icon.running)
        tr.set_title("x" * 300)
        self.assertEqual(len(tr.icon.title), 127)
        tr.notify("Finished: clip.mp4")
        self.assertEqual(tr.icon.notes, [("OpenDM", "Finished: clip.mp4")])
        tr.stop()
        self.assertFalse(tr.icon.running)

    def test_missing_pystray_degrades_cleanly(self):
        with mock.patch.dict(sys.modules, {"pystray": None}), mock.patch("opendm.platform.system", return_value="Linux"):
            tr = opendm.Tray(b"png")
        self.assertFalse(tr.available)
        self.assertIn("pip install pystray", tr.error)
        tr.start(); tr.set_title("x"); tr.notify("x"); tr.stop()  # all harmless no-ops
        self.assertEqual(tr.poll(), [])

    def test_macos_is_reported_unsupported(self):
        with mock.patch("opendm.platform.system", return_value="Darwin"):
            tr = opendm.Tray(b"png")
        self.assertFalse(tr.available)
        self.assertIn("macOS", tr.error)

    def test_a_desktop_without_a_tray_does_not_crash_start(self):
        tr = self.tray()
        tr.icon.run_detached = lambda: (_ for _ in ()).throw(RuntimeError("no tray host"))
        tr.start()
        self.assertFalse(tr.available)
        self.assertIn("no tray host", tr.error)


class TestIdmEngine(Base):
    def mgr(self):
        m = opendm.Manager(persist=False)
        m.settings["folder"] = self.tmp
        return m

    def test_list_formatting(self):
        self.assertEqual([opendm.fmt_left(x) for x in (None, 0, 12, 135, 3780, 90000)], ["", "0 sec", "12 sec", "2 min 15 sec", "1 h 03 min", "25 h 00 min"])
        self.assertEqual([opendm.fmt_rate(x) for x in (0, 500, 1536, 5 * 1024 ** 2, 3 * 1024 ** 3)], ["", "500 Bytes/sec", "1.5 KBytes/sec", "5.0 MBytes/sec", "3.0 GBytes/sec"])
        self.assertEqual(opendm.fmt_when(0), "")
        self.assertRegex(opendm.fmt_when(time.time()), r"^[A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4}$")

    def test_status_text(self):
        d = opendm.Download("http://x.test/a.zip", self.tmp)
        d.size, d.segs = 1000, [[0, 999, 250]]
        out = {}
        for st in ("Queued", "Connecting", "Downloading", "Paused", "Completed"):
            d.status = st
            out[st] = opendm.status_text(d)
        self.assertEqual(out, {"Queued": "Queued", "Connecting": "Connecting...", "Downloading": "25.00%", "Paused": "Stopped 25.0%", "Completed": "Complete"})
        d.status, d.error = "Error", "HTTP 404"
        self.assertEqual(opendm.status_text(d), "Error: HTTP 404")
        d.status, d.size = "Paused", -1
        d.segs = []
        self.assertEqual(opendm.status_text(d), "Stopped")

    def test_queue_numbers_skip_finished_downloads(self):
        m = self.mgr()
        a, b, c, e = (m.add(f"http://x.test/{n}.bin", self.tmp, later=True) for n in "abce")
        b.status = "Completed"
        m.add_queue("Night")
        m.move_to_queue(e, "Night")
        pos = opendm.queue_positions(m.items)
        self.assertEqual([pos.get(id(x)) for x in (a, b, c, e)], [1, None, 2, 1])

    def test_sorting_keys(self):
        m = self.mgr()
        a, b = m.add("http://x.test/b.bin", self.tmp, later=True), m.add("http://x.test/a.bin", self.tmp, later=True, desc="zeta")
        a.name, b.name, a.size, b.size = "b.bin", "a.bin", 10, 99
        qpos = opendm.queue_positions(m.items)
        for col, first in (("name", b), ("size", a), ("q", a), ("desc", a)):
            self.assertIs(min([a, b], key=lambda d: opendm.sort_key(d, col, qpos)), first, col)

    def test_new_downloads_get_queue_project_description_and_can_wait(self):
        m = self.mgr()
        m.add_queue("Night")
        d = m.add("http://cdn.example/a.zip", self.tmp, queue="Night", project="Holiday", later=True)
        e = m.add("http://x.test/b.zip", self.tmp, referer="https://page.example/watch?v=1", queue="Nope")
        self.assertEqual((d.queue, d.project, d.status, d.desc), ("Night", "Holiday", "Paused", "cdn.example"))
        self.assertEqual((e.queue, e.desc), (opendm.MAIN_QUEUE, "page.example"))  # unknown queue falls back; referer wins for the description
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))
        self.assertEqual((d2.queue, d2.project, d2.desc, d2.last_try), ("Night", "Holiday", "cdn.example", d.last_try))

    def test_queue_management(self):
        m = self.mgr()
        m.add_queue("Night")
        d = m.add("http://x.test/a.zip", self.tmp, queue="Night", later=True)
        for bad in ("", "a/b", "night", opendm.MAIN_QUEUE.upper(), "x" * 50):
            with self.assertRaises(ValueError, msg=bad):
                m.add_queue(bad)
        self.assertEqual(m.rename_queue("Night", "Weekend"), "Weekend")
        self.assertEqual(d.queue, "Weekend")
        with self.assertRaises(ValueError):
            m.rename_queue(opendm.MAIN_QUEUE, "x")
        self.assertEqual(m.start_queue("Weekend"), 1)
        self.assertEqual(d.status, "Queued")
        self.assertEqual(m.stop_queue("Weekend"), 1)
        self.assertEqual(d.status, "Paused")
        m.delete_queue("Weekend")
        self.assertEqual((d.queue, m.settings["queues"]), (opendm.MAIN_QUEUE, [opendm.MAIN_QUEUE]))
        with self.assertRaises(ValueError):
            m.delete_queue(opendm.MAIN_QUEUE)
        with self.assertRaises(ValueError):
            m.move_to_queue(d, "ghost")

    def test_filters_for_queues_and_projects(self):
        m = self.mgr()
        a = m.add("http://x.test/a.bin", self.tmp, later=True, project="P1")
        b = m.add("http://x.test/b.bin", self.tmp, later=True)
        b.status = "Completed"
        f = lambda flt: [opendm.matches_filter(d, flt) for d in (a, b)]
        self.assertEqual([f("queue:" + opendm.MAIN_QUEUE), f("queues"), f("project:P1"), f("projects"), f("all")],
                         [[True, False], [True, False], [True, False], [True, False], [True, True]])
        self.assertEqual(m.projects(), ["P1"])

    def test_export_and_import_round_trip(self):
        m = self.mgr()
        m.add_queue("Night")
        a = m.add("http://x.test/a.zip", self.tmp, queue="Night", project="P", desc="my note", later=True, cookie="secret=1")
        m.add("http://x.test/b.mp4", self.tmp, later=True)
        path = os.path.join(self.tmp, "export.json")
        self.assertEqual(m.export_list(path), 2)
        with open(path) as f:
            self.assertNotIn("secret", f.read())  # cookies are never written out
        m2 = self.mgr()
        m2.add_queue("Night")
        self.assertEqual(m2.import_list(path, self.tmp), 2)
        self.assertEqual([(d.url, d.queue, d.project, d.desc) for d in m2.items][0], ("http://x.test/a.zip", "Night", "P", "my note"))
        self.assertEqual(m2.import_list(path, self.tmp), 0)  # importing twice doesn't duplicate
        txt = os.path.join(self.tmp, "links.txt")
        with open(txt, "w") as f:
            f.write("see https://a.example/x.zip and\nhttps://a.example/x.zip again, plus https://b.example/y.pdf).\n")
        m3 = self.mgr()
        self.assertEqual(m3.import_list(txt, self.tmp), 2)
        self.assertEqual({d.status for d in m3.items}, {"Paused"})

    def test_delete_can_also_remove_the_finished_file(self):
        m = self.mgr()
        d = m.add(A("/files/report.pdf"), self.tmp, 1)
        t = time.time()
        while d.status != "Completed" and time.time() - t < 30:
            m.schedule()
            time.sleep(0.05)
        path = d.path
        m.remove(d)
        self.assertTrue(os.path.exists(path))  # default: only the list entry goes
        d2 = m.add(A("/files/data.zip"), self.tmp, 1)
        while d2.status != "Completed" and time.time() - t < 60:
            m.schedule()
            time.sleep(0.05)
        path2 = d2.path
        m.remove(d2, delete_completed=True)
        self.assertFalse(os.path.exists(path2))

    def test_link_extraction(self):
        links, title = opendm.extract_links('<title> My\n Page </title><a href="x.zip#frag">z</a><img src="//cdn.example/i.png"><img srcset="s1.jpg 1x, s2.jpg 2x">'
                                             '<a href="javascript:void(0)">j</a><a href="mailto:a@b.c">m</a><video poster="p.jpg" src="blob:xyz"></video>', "https://site.example/dir/")
        self.assertEqual(title, "My Page")
        self.assertEqual([u for _, u in links], ["https://site.example/dir/x.zip", "https://cdn.example/i.png", "https://site.example/dir/s1.jpg",
                                                 "https://site.example/dir/s2.jpg", "https://site.example/dir/p.jpg"])

    def test_grabber_filters_by_type_and_follows_one_level(self):
        pages = {"https://s.test/": '<title>T</title><a href="a.jpg">1</a><a href="b.mp4">2</a><a href="p2.html">next</a><a href="https://other.test/o.html">o</a><a href="x.css">css</a><a href="f.bin">f</a>',
                 "https://s.test/p2.html": '<a href="c.jpg">3</a><a href="a.jpg">dup</a>'}
        fetch = lambda u: (pages[u], u) if u in pages else (_ for _ in ()).throw(OSError("404"))
        files, title = opendm.grab_site("https://s.test/", {"jpg"}, depth=0, fetch=fetch)
        self.assertEqual((title, [f["name"] for f in files]), ("T", ["a.jpg"]))
        files, _ = opendm.grab_site("https://s.test/", {"jpg"}, depth=1, fetch=fetch)
        self.assertEqual([f["name"] for f in files], ["a.jpg", "c.jpg"])  # duplicates dropped, other sites not followed
        files, _ = opendm.grab_site("https://s.test/", {"jpg"}, depth=0, any_file=True, fetch=fetch)
        self.assertEqual([f["name"] for f in files], ["a.jpg", "b.mp4", "f.bin"])  # css and html pages are not "files"

    def test_grabber_against_a_real_web_server(self):
        files, title = opendm.grab_site(A("/site/index.html"), {"jpg", "png", "pdf", "zip"}, depth=1)
        self.assertEqual(title, "My Photos")
        self.assertEqual(sorted(f["name"] for f in files), ["a.jpg", "b.png", "deep.zip", "doc.pdf"])


class FakeWinreg:
    """Just enough of the Windows registry API (winreg) to test registration without Windows."""
    HKEY_CURRENT_USER, KEY_READ, REG_SZ = "HKCU", 1, 1

    class _Handle:
        def __init__(self, sub): self.sub = sub
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def __init__(self, existing=()):
        self.values, self.keys = {}, set()
        for k in existing:
            self._make(k)

    def _make(self, sub):
        parts = sub.split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.add("\\".join(parts[:i]))

    def CreateKey(self, root, sub):
        assert root == self.HKEY_CURRENT_USER, "must write under HKCU (no admin rights needed)"
        self._make(sub)
        return self._Handle(sub)

    def SetValueEx(self, h, name, reserved, typ, value):
        assert (name, typ) == ("", self.REG_SZ), "the manifest path must be the key's default REG_SZ value"
        self.values[h.sub] = value

    def OpenKey(self, root, sub, reserved=0, access=1):
        if sub not in self.keys:
            raise FileNotFoundError(sub)
        return self._Handle(sub)

    def QueryValueEx(self, h, name):
        if h.sub not in self.values:
            raise FileNotFoundError(h.sub)
        return self.values[h.sub], self.REG_SZ

    def DeleteKey(self, root, sub):
        if sub not in self.keys:
            raise FileNotFoundError(sub)
        self.keys.discard(sub)
        self.values.pop(sub, None)


CHROME_KEY = r"Software\Google\Chrome\NativeMessagingHosts\org.opendm.nativehost"
EDGE_KEY = r"Software\Microsoft\Edge\NativeMessagingHosts\org.opendm.nativehost"


class TestNativeRegistry(Base):
    """Windows registration, against a fake registry."""
    def ni(self, reg, **kw):
        kw.setdefault("executable", r"C:\Python312\python.exe")
        kw.setdefault("script", r"C:\OpenDM\opendm.py")
        return opendm.NativeIntegration(state_dir=self.tmp, system="Windows", winreg_module=reg, **kw)

    def manifest(self, reg, key):
        with open(reg.values[key], encoding="utf-8") as f:
            return json.load(f)

    def test_chrome_and_edge_are_registered_under_hkcu(self):
        reg = FakeWinreg()
        res = self.ni(reg).register()
        self.assertEqual(sorted(reg.values), sorted([CHROME_KEY, EDGE_KEY]))  # exactly the two browsers asked for; nothing else is detected
        self.assertEqual({r["key"]: r["registered"] for r in res}, {"chrome": True, "edge": True, "brave": False, "chromium": False, "firefox": False})
        m = self.manifest(reg, CHROME_KEY)
        self.assertEqual((m["name"], m["type"], m["allowed_origins"]), ("org.opendm.nativehost", "stdio", [f"chrome-extension://{opendm.DEFAULT_EXTENSION_IDS[0]}/"]))
        self.assertEqual(self.manifest(reg, EDGE_KEY)["allowed_origins"], m["allowed_origins"])
        self.assertTrue(m["path"].endswith("opendm-host.bat") and os.path.isabs(m["path"]))

    def test_the_launcher_batch_file_is_what_a_browser_can_run(self):
        reg = FakeWinreg()
        self.ni(reg).register()
        with open(self.manifest(reg, CHROME_KEY)["path"], newline="") as f:
            bat = f.read()
        self.assertEqual(bat, '@echo off\r\n"C:\\Python312\\python.exe" "C:\\OpenDM\\opendm.py" %*\r\n')  # @echo off keeps cmd from polluting the protocol; %* forwards the origin

    def test_pythonw_is_swapped_for_a_console_python(self):
        os.makedirs(os.path.join(self.tmp, "py"))
        for n in ("pythonw.exe", "python.exe"):
            open(os.path.join(self.tmp, "py", n), "w").close()
        reg = FakeWinreg()
        self.ni(reg, executable=os.path.join(self.tmp, "py", "pythonw.exe")).register()
        with open(self.manifest(reg, CHROME_KEY)["path"], newline="") as f:
            self.assertIn(os.path.join(self.tmp, "py", "python.exe"), f.read())

    def test_frozen_exe_registers_itself(self):
        reg = FakeWinreg()
        self.ni(reg, frozen=True, executable=r"C:\Apps\OpenDM.exe").register()
        self.assertEqual(self.manifest(reg, CHROME_KEY)["path"], r"C:\Apps\OpenDM.exe")  # no wrapper needed

    def test_other_browsers_only_when_their_vendor_key_exists(self):
        reg = FakeWinreg(existing=[r"Software\BraveSoftware\Brave-Browser", r"Software\Mozilla"])
        self.ni(reg).register()
        self.assertIn(r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\org.opendm.nativehost", reg.values)
        fx = self.manifest(reg, r"Software\Mozilla\NativeMessagingHosts\org.opendm.nativehost")
        self.assertEqual(fx["allowed_extensions"], ["opendm@example.org"])
        self.assertNotIn("allowed_origins", fx)
        self.assertNotIn(r"Software\Chromium\NativeMessagingHosts\org.opendm.nativehost", reg.values)

    def test_status_register_repair_and_unregister(self):
        reg = FakeWinreg()
        states = lambda ni: {r["key"]: r["state"] for r in ni.status()}
        ni = self.ni(reg)
        self.assertEqual(states(ni)["chrome"], "not registered")
        self.assertEqual(states(ni)["brave"], "browser not found")
        ni.register()
        self.assertEqual((states(ni)["chrome"], states(ni)["edge"]), ("registered", "registered"))
        moved = self.ni(reg, script=r"D:\Moved\opendm.py")  # the app was moved: the registration is now out of date
        self.assertEqual(states(moved)["chrome"], "outdated")
        moved.register()
        self.assertEqual(states(moved)["chrome"], "registered")
        moved.unregister()
        self.assertEqual((reg.values, states(moved)["chrome"]), ({}, "not registered"))

    def test_registering_twice_changes_nothing(self):
        reg = FakeWinreg()
        ni = self.ni(reg)
        ni.register()
        snapshot, mt = dict(reg.values), os.path.getmtime(reg.values[CHROME_KEY])
        time.sleep(0.05)
        ni.register()
        self.assertEqual((reg.values, os.path.getmtime(reg.values[CHROME_KEY])), (snapshot, mt))  # not even rewritten

    def test_extra_extension_ids_are_validated(self):
        store_id = "a" * 32
        reg = FakeWinreg()
        self.ni(reg, extra_ids=[store_id, "NOT-AN-ID", "q" * 32, store_id.upper()]).register()
        self.assertEqual(self.manifest(reg, CHROME_KEY)["allowed_origins"],
                         [f"chrome-extension://{opendm.DEFAULT_EXTENSION_IDS[0]}/", f"chrome-extension://{store_id}/"])


@unittest.skipIf(os.name == "nt", "registers by writing a shell launcher: the Windows path is covered by TestNativeRegistry")
class TestNativeFiles(Base):
    """Linux/macOS registration is file based, so this one can be tested for real, including running the registered host."""
    def setUp(self):
        super().setUp()
        self.home, self.state = os.path.join(self.tmp, "home"), os.path.join(self.tmp, "state")
        for d in (".config/google-chrome", ".mozilla"):
            os.makedirs(os.path.join(self.home, d))
        self.ni = opendm.NativeIntegration(state_dir=self.state, home=self.home, system="Linux")

    def chrome_manifest(self):
        return os.path.join(self.home, ".config/google-chrome/NativeMessagingHosts/org.opendm.nativehost.json")

    def test_manifests_are_written_only_for_installed_browsers(self):
        res = {r["key"]: r for r in self.ni.register()}
        self.assertEqual({k: v["registered"] for k, v in res.items()}, {"chrome": True, "edge": False, "brave": False, "chromium": False, "firefox": True})
        self.assertEqual(res["edge"]["detail"], "browser not found")
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config/microsoft-edge")))  # didn't litter folders of browsers that aren't there
        self.assertTrue(os.path.exists(os.path.join(self.home, ".mozilla/native-messaging-hosts/org.opendm.nativehost.json")))
        with open(self.chrome_manifest()) as f:
            m = json.load(f)
        self.assertTrue(os.access(m["path"], os.X_OK))

    def test_the_registered_host_really_works_when_a_browser_starts_it(self):
        self.ni.register()
        with open(self.chrome_manifest()) as f:
            m = json.load(f)
        origin = m["allowed_origins"][0]  # exactly what Chrome passes as the first argument
        p = subprocess.run([m["path"], origin], input=_frame({"cmd": "ping"}) + _frame({"cmd": "nonsense"}), capture_output=True, timeout=30,
                           env={**os.environ, "OPENDM_HOME": self.state})
        self.assertEqual(p.returncode, 0, p.stderr)
        replies = _unframe(p.stdout)
        self.assertEqual((replies[0]["ok"], replies[0]["app"], replies[0]["running"]), (True, "OpenDM", False))
        self.assertEqual(replies[1], {"ok": False, "error": "Unknown command."})
        self.assertEqual(len(replies), 2)  # nothing but protocol bytes on stdout

    def test_a_stranger_is_turned_away(self):
        self.ni.register()
        with open(self.chrome_manifest()) as f:
            m = json.load(f)
        p = subprocess.run([m["path"], "chrome-extension://" + "b" * 32 + "/"], input=_frame({"cmd": "ping"}), capture_output=True, timeout=30,
                           env={**os.environ, "OPENDM_HOME": self.state})
        self.assertEqual((p.returncode, p.stdout), (2, b""))

    def test_command_line_switches(self):
        env = {**os.environ, "HOME": self.home, "OPENDM_HOME": self.state}
        run = lambda *a: subprocess.run([sys.executable, os.path.join(os.path.dirname(opendm.__file__), "opendm.py"), *a], capture_output=True, text=True, env=env, timeout=30)
        p = run("--register-browsers", "--extension-id", "c" * 32)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Google Chrome", p.stdout)
        with open(self.chrome_manifest()) as f:
            self.assertIn("c" * 32, f.read())
        self.assertEqual(read_settings(self.state)["extension_ids"], ["c" * 32])
        self.assertEqual(run("--unregister-browsers").returncode, 0)
        self.assertFalse(os.path.exists(self.chrome_manifest()))


def _frame(obj):
    import struct
    data = json.dumps(obj).encode()
    return struct.pack("=I", len(data)) + data


def _unframe(raw):
    import struct
    out, i = [], 0
    while i < len(raw):
        (n,) = struct.unpack("=I", raw[i:i + 4])
        out.append(json.loads(raw[i + 4:i + 4 + n]))
        i += 4 + n
    return out


def read_settings(state):
    with open(os.path.join(state, "settings.json")) as f:
        return json.load(f)


class TestNativeHost(Base):
    def setUp(self):
        super().setUp()
        self.state = os.path.join(self.tmp, "state")
        self.token = opendm.get_token(self.state)
        self.mgr, self.port = opendm.Manager(persist=False), free_port()
        self.srv = self.start_api()
        self.host = opendm.NativeHost(state_dir=self.state, launch=lambda: self.fail("must not launch"), sleep=lambda s: None)

    def start_api(self):
        srv = opendm.start_api(self.mgr, lambda: (self.tmp, 2), port=self.port, token=self.token, state_dir=self.state)
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv

    def stop_api(self):
        self.srv.shutdown()
        self.srv.server_close()

    def serve(self, messages, args=("chrome-extension://" + opendm.DEFAULT_EXTENSION_IDS[0] + "/",), host=None):
        import io
        out = io.BytesIO()
        code = (host or self.host).serve(list(args), io.BytesIO(b"".join(m if isinstance(m, bytes) else _frame(m) for m in messages)), out)
        return code, _unframe(out.getvalue())

    def test_the_port_comes_from_the_hint_file_not_a_fixed_number(self):
        self.assertEqual(self.host.port(), self.port)
        self.assertNotEqual(self.port, opendm.API_PORT)

    def test_ping_reports_status_without_starting_anything(self):
        code, r = self.serve([{"cmd": "ping"}])
        self.assertEqual((code, r[0]["ok"], r[0]["running"], r[0]["port"], r[0]["version"]), (0, True, True, self.port, opendm.__version__))

    def test_add_reaches_opendm_with_no_token_from_the_extension(self):
        job = {"url": "https://x.test/a.zip", "referer": "https://x.test/", "filename": "My file.zip", "cookie": "sid=1", "userAgent": "UA/1",
               "evil": "ignored", "kind": "", "quality": 0}
        code, r = self.serve([{"cmd": "add", "job": job}])
        self.assertEqual((code, r), (0, [{"ok": True}]))
        d = self.mgr.items[0]
        self.assertEqual((d.url, d.referer, d.cookie, d.ua, d.hint), ("https://x.test/a.zip", "https://x.test/", "sid=1", "UA/1", "My file.zip"))
        for x in self.mgr.items:
            x.pause()

    def test_hls_and_merge_jobs_keep_their_options(self):
        self.serve([{"cmd": "add", "job": {"url": "https://x.test/m.m3u8", "kind": "hls", "quality": 720, "bandwidth": 900000}},
                    {"cmd": "add", "job": {"url": "https://x.test/v.mp4", "audioUrl": "https://x.test/a.m4a", "filename": "Clip 720p.mp4"}}])
        h, m = self.mgr.items
        self.assertEqual((type(h).__name__, h.quality, h.pick_bw, type(m).__name__, m.audio_url), ("HlsDownload", 720, 900000, "MuxDownload", "https://x.test/a.m4a"))
        for x in self.mgr.items:
            x.pause()

    def test_bad_requests_get_clear_errors(self):
        _, r = self.serve([{"cmd": "add", "job": {"url": "file:///etc/passwd"}}, {"cmd": "add"}, {"cmd": "add", "job": {"url": "ftp://x/y"}}, {"cmd": "bogus"}, ["not", "a", "dict"]])
        self.assertEqual([x["ok"] for x in r], [False] * 5)
        self.assertIn("web address", r[0]["error"])
        self.assertEqual(self.mgr.items, [])

    def test_only_registered_extensions_may_call(self):
        evil = "chrome-extension://" + "z" * 31 + "a/"
        self.assertEqual(self.serve([{"cmd": "ping"}], args=(evil,)), (2, []))
        self.assertEqual(self.serve([{"cmd": "ping"}], args=("moz-extension://abc/",)), (2, []))
        fx = ("/x/org.opendm.nativehost.json", "opendm@example.org")
        self.assertEqual(self.serve([{"cmd": "ping"}], args=fx)[0], 0)
        self.assertEqual(self.serve([{"cmd": "ping"}], args=("/x/org.opendm.nativehost.json", "evil@example.org"))[0], 2)
        self.assertEqual(self.serve([{"cmd": "ping"}], args=("--native-host",))[0], 0)  # started by hand for testing
        store = "d" * 32  # a store ID added in Browser setup is accepted afterwards
        self.assertEqual(self.serve([{"cmd": "ping"}], args=(f"chrome-extension://{store}/",))[0], 2)
        with open(os.path.join(self.state, "settings.json"), "w") as f:
            json.dump({"extension_ids": [store]}, f)
        self.assertEqual(self.serve([{"cmd": "ping"}], args=(f"chrome-extension://{store}/",))[0], 0)

    def test_broken_framing_is_reported_and_ends_the_session(self):
        import struct
        code, r = self.serve([struct.pack("=I", opendm.MAX_NATIVE_MESSAGE + 1)])
        self.assertEqual((code, r[0]["ok"]), (1, False))
        code, r = self.serve([struct.pack("=I", 50) + b"short"])
        self.assertEqual((code, r[0]["ok"]), (1, False))
        code, r = self.serve([struct.pack("=I", 5) + b"{oops"])
        self.assertEqual((code, r[0]["ok"]), (1, False))

    def test_opendm_is_started_when_it_is_not_running(self):
        self.stop_api()
        launched = []

        def launch():  # stands in for starting the real window: the server comes up a moment later
            launched.append(1)
            threading.Timer(0.3, self.start_api).start()
        host = opendm.NativeHost(state_dir=self.state, launch=launch, wait_seconds=10)
        code, r = self.serve([{"cmd": "add", "job": {"url": "https://x.test/late.zip"}}], host=host)
        self.assertEqual((r, launched, [d.url for d in self.mgr.items]), ([{"ok": True}], [1], ["https://x.test/late.zip"]))
        for x in self.mgr.items:
            x.pause()

    def test_autostart_can_be_switched_off(self):
        self.stop_api()
        with open(os.path.join(self.state, "settings.json"), "w") as f:
            json.dump({"autostart_from_browser": False}, f)
        _, r = self.serve([{"cmd": "add", "job": {"url": "https://x.test/a.zip"}}])
        self.assertFalse(r[0]["ok"])
        self.assertIn("isn't running", r[0]["error"])
        self.assertEqual(self.serve([{"cmd": "ping"}])[1][0]["running"], False)

    def test_an_app_that_never_starts_gives_up_politely(self):
        self.stop_api()
        host = opendm.NativeHost(state_dir=self.state, launch=lambda: None, wait_seconds=0.4)
        _, r = self.serve([{"cmd": "add", "job": {"url": "https://x.test/a.zip"}}], host=host)
        self.assertIn("did not become ready", r[0]["error"])

    def test_token_mismatch_is_explained(self):
        with open(os.path.join(self.state, "token"), "w") as f:
            f.write("a-different-token")
        _, r = self.serve([{"cmd": "add", "job": {"url": "https://x.test/a.zip"}}])
        self.assertFalse(r[0]["ok"])
        self.assertIn("token", r[0]["error"])

    def test_wire_format_round_trip(self):
        import io
        b = io.BytesIO()
        opendm.nm_write(b, {"héllo": "wörld ✓"})
        b.seek(0)
        self.assertEqual((opendm.nm_read(b), opendm.nm_read(b)), ({"héllo": "wörld ✓"}, None))

    def test_ids_and_manifests_agree(self):
        root = os.path.join(os.path.dirname(os.path.abspath(opendm.__file__)), "extension")
        with open(os.path.join(root, "manifest.json")) as f:
            chrome = json.load(f)
        with open(os.path.join(root, "manifest.firefox.json")) as f:
            firefox = json.load(f)
        import base64, hashlib
        derived = "".join(chr(97 + int(c, 16)) for c in hashlib.sha256(base64.b64decode(chrome["key"])).hexdigest()[:32])
        self.assertEqual(derived, opendm.DEFAULT_EXTENSION_IDS[0])  # the "key" in the manifest really produces the ID OpenDM trusts
        self.assertEqual(firefox["browser_specific_settings"]["gecko"]["id"], opendm.FIREFOX_EXTENSION_ID)
        self.assertIn("nativeMessaging", chrome["permissions"])
        self.assertIn("nativeMessaging", firefox["permissions"])
        self.assertNotIn("key", firefox)

    def test_how_a_browser_launch_is_recognised(self):
        f = opendm.is_native_host_launch
        self.assertEqual([f(["opendm.py"] + a) for a in ([], ["https://x/y.zip"], ["-o", "dir"], ["chrome-extension://abc/"], ["chrome-extension://abc/", "--parent-window=123"],
                                                            ["--native-host"], ["C:\\x\\org.opendm.nativehost.json", "opendm@example.org"], ["other.json", "x"])],
                         [False, False, False, True, True, True, True, False])
        self.assertEqual(opendm.launch_command(frozen=True, executable="/o/OpenDM"), ["/o/OpenDM", "--minimized"])
        self.assertEqual(opendm.launch_command(frozen=False, executable="/usr/bin/python3", script="/o/opendm.py"), ["/usr/bin/python3", "/o/opendm.py", "--minimized"])


class FakeCanvas:
    """Records draw calls so the chart code can be checked without a display."""
    def __init__(self, w=600, h=125):
        self.w, self.h, self.calls = w, h, []

    def winfo_width(self): return self.w
    def winfo_height(self): return self.h
    def delete(self, *a): self.calls.append(("delete",))
    def __getattr__(self, name):
        if name.startswith("create_"):
            return lambda *a, **k: self.calls.append((name, a, k))
        raise AttributeError(name)

    def kinds(self, kind): return [c for c in self.calls if c[0] == kind]


class TestGraph(Base):
    def test_axis_maximum_is_tidy(self):
        K, M = 1024, 1024 ** 2
        self.assertEqual(opendm.nice_max(0), 1024)
        self.assertEqual(opendm.nice_max(300 * K), 400 * K)
        self.assertEqual(opendm.nice_max(3.2 * M), 4 * M)
        self.assertEqual(opendm.nice_max(9 * M), 10 * M)
        self.assertGreaterEqual(opendm.nice_max(123456789), 123456789)

    def test_stats(self):
        self.assertEqual(opendm.graph_stats([1, 2, 3, 10]), (10, 10, 4.0))
        self.assertEqual(opendm.graph_stats([]), (0.0, 0.0, 0.0))
        self.assertEqual(opendm.graph_stats(list(range(100)), 10)[2], 94.5)  # only the last 10 samples count

    def test_http_segment_map(self):
        d = opendm.Download("http://x.test/f", self.tmp)
        d.size, d.segs = 1000, [[500, 999, 500], [0, 499, 250]]
        self.assertEqual(d.segment_map(), [(0, 0.5, 0.25), (0.5, 1.0, 0.5)])

    def test_hls_segment_map_merges_runs(self):
        d = opendm.HlsDownload("http://x.test/a.m3u8", self.tmp)
        d.flags = bytearray([1, 1, 0, 0])
        self.assertEqual(d.segment_map(), [(0, 0.5, 0.5), (0.5, 1.0, 0.5)])
        d.flags = bytearray([0, 1, 1, 1])
        self.assertEqual(d.segment_map(), [(0, 0.25, 0.0), (0.25, 1.0, 1.0)])

    def test_speed_history_and_no_spike_after_restart(self):
        d = opendm.Download("http://x.test/f", self.tmp)
        d.size, d.segs, d._last = 4_000_000, [[0, 3_999_999, 2_000_000]], (time.time() - 2, 0)
        d.update_speed()
        self.assertAlmostEqual(d.hist[-1], 1_000_000, delta=150_000)
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))
        self.assertEqual(d2._last[1], d2.done)  # a paused download reloaded with 2 MB done must not read as 2 MB/s

    def test_total_history_is_sampled_once_a_second(self):
        m = opendm.Manager(persist=False)
        d = m.add("http://x.test/f", self.tmp)
        d.speed = 1234.0
        m.schedule(); m.schedule()
        self.assertEqual(list(m.hist), [1234.0])

    def test_chart_draws_grid_line_and_fill(self):
        cv = FakeCanvas()
        opendm.draw_graph(cv, [0, 1e6, 2e6, 1.5e6])
        self.assertEqual(len(cv.kinds("create_polygon")), 1)
        self.assertEqual(len(cv.kinds("create_line")), 5 + 1)           # 5 grid lines + the speed line
        labels = [c[2]["text"] for c in cv.kinds("create_text")]
        self.assertIn("now", labels)
        self.assertTrue(any(l.endswith("MB/s") for l in labels), labels)
        empty = FakeCanvas()
        opendm.draw_graph(empty, [])                                    # no data yet: axes only, no crash
        self.assertEqual(len(empty.kinds("create_polygon")), 0)

    def test_segment_bar(self):
        cv = FakeCanvas(w=1000, h=16)
        opendm.draw_segmap(cv, [(0, 0.5, 0.25), (0.5, 1.0, 0.5)])
        rects = cv.kinds("create_rectangle")
        self.assertEqual(len(rects), 3)                                  # 2 segment boxes + 1 filled part
        self.assertEqual(rects[1][1][:3], (0.0, 1, 250.0))               # filled to a quarter of the width
        none = FakeCanvas(); opendm.draw_segmap(none, [])
        self.assertIn("Select a single download", none.kinds("create_text")[0][2]["text"])


class TestAssets(unittest.TestCase):
    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

    def test_embedded_window_icon_is_a_png(self):
        import base64
        self.assertEqual(base64.b64decode("".join(opendm.ICON_B64))[:8], b"\x89PNG\r\n\x1a\n")

    def test_extension_manifests_point_to_existing_icons(self):
        for name in ("manifest.json", "manifest.firefox.json"):
            with open(os.path.join(self.ROOT, "extension", name)) as f:
                m = json.load(f)
            self.assertEqual(sorted(m["icons"]), ["128", "16", "32", "48"])
            for path in m["icons"].values():
                self.assertTrue(os.path.isfile(os.path.join(self.ROOT, "extension", path)), path)

    def test_app_icons_exist(self):
        for f in ("icon.png", "icon.ico", "icon.icns"):
            self.assertGreater(os.path.getsize(os.path.join(self.ROOT, "assets", f)), 1000)


if __name__ == "__main__":
    unittest.main()
