import os, sqlite3, secrets, csv, io
from datetime import datetime, date
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort, send_file
from werkzeug.security import generate_password_hash, check_password_hash

ROOT=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.path.join(ROOT,'sia_smamla.db')
app=Flask(__name__)
app.secret_key=os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

def db():
    c=sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def col_exists(c,t,n):
    return any(x['name']==n for x in c.execute(f'PRAGMA table_info({t})'))

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,nama TEXT NOT NULL,linked_id INTEGER,aktif INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS kelas(id INTEGER PRIMARY KEY AUTOINCREMENT,nama TEXT UNIQUE NOT NULL,wali_kelas TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS guru(id INTEGER PRIMARY KEY AUTOINCREMENT,nip TEXT UNIQUE,nama TEXT NOT NULL,email TEXT DEFAULT '',no_hp TEXT DEFAULT '',alamat TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS siswa(id INTEGER PRIMARY KEY AUTOINCREMENT,nis TEXT UNIQUE NOT NULL,nama TEXT NOT NULL,kelas_id INTEGER,jk TEXT DEFAULT '',email TEXT DEFAULT '',no_hp TEXT DEFAULT '',alamat TEXT DEFAULT '',FOREIGN KEY(kelas_id) REFERENCES kelas(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS mapel(id INTEGER PRIMARY KEY AUTOINCREMENT,kode TEXT UNIQUE,nama TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jadwal(id INTEGER PRIMARY KEY AUTOINCREMENT,kelas_id INTEGER,mapel_id INTEGER,guru_id INTEGER,hari TEXT NOT NULL,jam_mulai TEXT NOT NULL,jam_selesai TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS presensi(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,nama TEXT NOT NULL,role TEXT NOT NULL,tanggal TEXT NOT NULL,waktu TEXT NOT NULL,status TEXT NOT NULL,catatan TEXT DEFAULT '',UNIQUE(user_id,tanggal));
        CREATE TABLE IF NOT EXISTS aktivitas(id INTEGER PRIMARY KEY AUTOINCREMENT,user TEXT,aksi TEXT,waktu TEXT);
        CREATE TABLE IF NOT EXISTS nilai(id INTEGER PRIMARY KEY AUTOINCREMENT,siswa_id INTEGER NOT NULL,mapel_id INTEGER NOT NULL,semester TEXT NOT NULL,tahun_ajaran TEXT NOT NULL,nilai_uts REAL NOT NULL,nilai_uas REAL NOT NULL,catatan TEXT DEFAULT '',UNIQUE(siswa_id,mapel_id,semester,tahun_ajaran),FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,FOREIGN KEY(mapel_id) REFERENCES mapel(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS keuangan(id INTEGER PRIMARY KEY AUTOINCREMENT,siswa_id INTEGER NOT NULL,tanggal TEXT NOT NULL,jenis TEXT NOT NULL,nominal INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'Belum Lunas',keterangan TEXT DEFAULT '',FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE);
        """)
        if not col_exists(c,'users','linked_id'): c.execute('ALTER TABLE users ADD COLUMN linked_id INTEGER')
        if not col_exists(c,'users','wajib_ganti'): c.execute('ALTER TABLE users ADD COLUMN wajib_ganti INTEGER DEFAULT 0')
        if not col_exists(c,'presensi','validasi'): c.execute("ALTER TABLE presensi ADD COLUMN validasi TEXT DEFAULT 'Menunggu'")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_siswa ON users(linked_id) WHERE role='siswa' AND linked_id IS NOT NULL")
        if not c.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
            c.execute("INSERT INTO users(username,password,role,nama) VALUES(?,?,?,?)",('admin',generate_password_hash('admin123'),'admin','Administrator'))
        if not c.execute('SELECT 1 FROM kelas LIMIT 1').fetchone():
            c.execute("INSERT INTO kelas(nama,wali_kelas) VALUES('X IPA 1','Belum ditentukan')")
        if not c.execute('SELECT 1 FROM mapel LIMIT 1').fetchone():
            c.execute("INSERT INTO mapel(kode,nama) VALUES('INF','Informatika')")
        # One-to-one student login: username = NIS; temporary password = NIS + @SMA
        for s in c.execute('SELECT * FROM siswa').fetchall():
            u=c.execute("SELECT id FROM users WHERE role='siswa' AND linked_id=?",(s['id'],)).fetchone()
            if not u:
                old=c.execute("SELECT id FROM users WHERE role='siswa' AND username=? AND linked_id IS NULL",(s['nis'],)).fetchone()
                pw=s['nis']+'@SMA'
                if old:
                    c.execute("UPDATE users SET username=?,nama=?,linked_id=?,password=?,wajib_ganti=1 WHERE id=?",(s['nis'],s['nama'],s['id'],generate_password_hash(pw),old['id']))
                else:
                    # Avoid binding an unrelated generic demo account to a real student.
                    c.execute("INSERT INTO users(username,password,role,nama,linked_id,wajib_ganti) VALUES(?,?,?,?,?,1)",(s['nis'],generate_password_hash(pw),'siswa',s['nama'],s['id']))
        c.commit()

def log(aksi):
    with db() as c: c.execute('INSERT INTO aktivitas(user,aksi,waktu) VALUES(?,?,?)',(session.get('nama','Sistem'),aksi,datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get('uid'): return redirect(url_for('login'))
        return f(*a,**k)
    return w
def roles(*r):
    def deco(f):
        @wraps(f)
        def w(*a,**k):
            if session.get('role') not in r: abort(403)
            return f(*a,**k)
        return w
    return deco

STYLE=r"""
:root{--navy:#101b3d;--blue:#365cf5;--cyan:#19b7c9;--bg:#f4f7fc;--ink:#18233f;--muted:#77829a;--line:#e7ecf4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:15px Inter,Segoe UI,Arial,sans-serif;color:var(--ink)}
a{text-decoration:none;color:inherit}.layout{display:flex;min-height:100vh}.side{width:250px;background:linear-gradient(165deg,#101b3d,#172c60);color:#fff;padding:25px 17px;position:fixed;inset:0 auto 0 0;overflow:auto}.brand{font-weight:800;font-size:18px;line-height:1.4;padding:0 12px 25px}.brand small{display:block;color:#aebde5;font-size:11px;letter-spacing:2px;margin-top:5px}.navlabel{color:#8294c3;font-size:10px;font-weight:800;letter-spacing:1.5px;padding:14px 12px 8px}.nav a{display:block;padding:11px 13px;margin:3px 0;border-radius:11px;color:#dbe4ff;font-size:13px}.nav a:hover,.nav a.active{background:#ffffff1c;color:#fff}.main{margin-left:250px;flex:1;min-width:0;max-width:calc(100vw - 250px);padding:28px 34px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px}.top h1{font-size:25px;margin:0}.muted{color:var(--muted)}.userpill{background:white;border:1px solid var(--line);padding:10px 14px;border-radius:14px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:16px}.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:21px;box-shadow:0 8px 28px #233b6810;margin-bottom:18px;max-width:100%;overflow:hidden}.stat{font-size:28px;font-weight:800;margin:12px 0 4px}.statlabel{font-size:12px;color:var(--muted)}.card h3{margin:0 0 17px;font-size:16px}.btn{border:0;border-radius:10px;padding:10px 15px;background:var(--blue);color:white;font-weight:700;cursor:pointer;display:inline-block;font-size:13px}.btn.secondary{background:#edf1ff;color:#3151d5}.btn.danger{background:#fff0f0;color:#d23d4b}.btn.dark{background:var(--navy)}input,select,textarea{width:100%;border:1px solid #dce3ef;border-radius:10px;padding:11px 12px;margin:6px 0 14px;font:inherit;background:#fff}label{font-size:12px;font-weight:700;color:#58647d}table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:#7b879d;font-size:11px;text-transform:uppercase;letter-spacing:.5px;background:#f8faff}td,th{padding:13px 11px;border-bottom:1px solid var(--line)}tr:last-child td{border:0}.tablewrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}table{min-width:100%}.flash{padding:12px 15px;border-radius:11px;background:#edf4ff;margin-bottom:12px;font-size:13px}.flash.danger{background:#fff0f0;color:#a62e3a}.flash.success{background:#eaf9f1;color:#18764b}.flash.warning{background:#fff7e6;color:#92620a}.tag{display:inline-block;padding:5px 9px;border-radius:20px;background:#edf2ff;color:#3654c9;font-size:11px;font-weight:700}.actions{display:flex;gap:7px;flex-wrap:wrap}.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.login{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 15% 20%,#4269ff,#101b3d 65%);padding:20px}.loginbox{background:#fff;border-radius:24px;padding:38px;width:min(430px,100%);box-shadow:0 25px 90px #07102b66}.loginbox h1{margin:0 0 8px;font-size:25px}.loginbox .btn{width:100%;padding:13px}.notice{font-size:12px;color:#77829a;line-height:1.7}.mobilemenu{display:none}@media(max-width:850px){.side{position:static;width:100%;height:auto}.layout{display:block}.main{margin:0;width:100%;max-width:100%;padding:20px}.nav{display:grid;grid-template-columns:repeat(2,1fr)}.formgrid{grid-template-columns:1fr}.top{align-items:flex-start;gap:12px;flex-direction:column}}
"""
BASE=r"""
<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}} | Portal Akademik SMA Muhammadiyah Lemahabang</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script><style>"""+STYLE+r"""</style></head><body>
{% if session.get('uid') %}<div class="layout"><aside class="side"><div class="brand">PORTAL<span style="color:#5ce0e5">.</span><small>AKADEMIK SMA MUHAMMADIYAH LEMAHABANG</small></div><div class="nav">
<div class="navlabel">MENU UTAMA</div><a href="{{url_for('dashboard')}}">▦ Dashboard</a><a href="{{url_for('attendance')}}">◷ Presensi</a><a href="{{url_for('schedule')}}">▤ Jadwal Pelajaran</a>
{% if session.get('role') in ['admin','guru'] %}<div class="navlabel">AKADEMIK</div><a href="{{url_for('students')}}">♙ Data Siswa</a><a href="{{url_for('teachers')}}">♧ Data Guru</a><a href="{{url_for('classes')}}">▦ Data Kelas</a><a href="{{url_for('subjects')}}">▣ Mata Pelajaran</a><a href="{{url_for('grades')}}">★ Nilai Akademik</a>{% endif %}
{% if session.get('role')=='admin' %}<div class="navlabel">MANAJEMEN</div><a href="{{url_for('accounts')}}">◎ Akun & Password</a><a href="{{url_for('finance')}}">Rp Keuangan</a><a href="{{url_for('reports')}}">▥ Laporan & Export Excel</a>{% endif %}
<div class="navlabel">AKUN SAYA</div><a href="{{url_for('change_password')}}">⚙ Ganti Password</a><a href="{{url_for('logout')}}">↪ Keluar</a></div></aside>
<main class="main"><div class="top"><div><h1>{{title}}</h1><div class="muted" style="font-size:12px;margin-top:5px">SMA Muhammadiyah Lemahabang · Sistem Informasi Akademik</div></div><div class="userpill">● {{session.get('nama')}} · {{session.get('role','').upper()}}</div></div>
{% with messages=get_flashed_messages(with_categories=true) %}{% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}
{{content|safe}}</main></div>
{% else %}{{content|safe}}{% endif %}</body></html>"""
def page(title,body,**ctx):
    inner=render_template_string(body,**ctx)
    return render_template_string(BASE,title=title,content=inner)

@app.route('/')
def index(): return redirect(url_for('dashboard') if session.get('uid') else url_for('login'))
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        un=request.form.get('username','').strip()
        pw=request.form.get('password','').strip()
        with db() as c:
            student=c.execute('SELECT * FROM siswa WHERE TRIM(nis)=?',(un,)).fetchone()
            if student:
                linked=c.execute("SELECT * FROM users WHERE role='siswa' AND linked_id=?",(student['id'],)).fetchone()
                temp_password=f"{student['nis'].strip()}@SMA"
                if not linked:
                    collision=c.execute('SELECT * FROM users WHERE username=?',(un,)).fetchone()
                    if collision and collision['role']=='siswa' and collision['linked_id'] is None:
                        c.execute("UPDATE users SET nama=?,linked_id=?,password=?,wajib_ganti=1,aktif=1 WHERE id=?",
                                  (student['nama'],student['id'],generate_password_hash(temp_password),collision['id']))
                    elif not collision:
                        c.execute("INSERT INTO users(username,password,role,nama,linked_id,wajib_ganti,aktif) VALUES(?,?,?,?,?,1,1)",
                                  (un,generate_password_hash(temp_password),'siswa',student['nama'],student['id']))
                else:
                    c.execute("UPDATE users SET aktif=1 WHERE id=?",(linked['id'],))
                    if linked['username'] != un and not c.execute('SELECT 1 FROM users WHERE username=?',(un,)).fetchone():
                        c.execute('UPDATE users SET username=? WHERE id=?',(un,linked['id']))

            u=c.execute('SELECT * FROM users WHERE username=? AND aktif=1',(un,)).fetchone()

            is_valid=False
            if u:
                if check_password_hash(u['password'],pw):
                    is_valid=True
                elif u['role']=='siswa' and u['wajib_ganti']==1 and pw.lower()==f"{un.lower()}@sma":
                    is_valid=True

        if u and is_valid:
            if u['role']=='siswa' and not u['linked_id']:
                flash('Akun demo siswa belum terhubung ke data NIS. Gunakan NIS siswa untuk login.','warning')
                return redirect(url_for('login'))
            session.clear(); session.update(uid=u['id'],username=u['username'],role=u['role'],nama=u['nama'])
            log('Login')
            if u['role']=='siswa' and u['wajib_ganti']: return redirect(url_for('change_password'))
            return redirect(url_for('dashboard'))
        flash('Username/NIS atau password salah. Belum punya akun? Klik daftar akun siswa di bawah.','danger')
    return page('Login',r"""<div class="login"><div class="loginbox"><div style="font-size:12px;letter-spacing:2px;color:#4261e9;font-weight:800">PORTAL AKADEMIK · SMAMLA</div><h1>Selamat Datang</h1><p class="muted">Masuk ke Portal Akademik SMA Muhammadiyah Lemahabang</p>{% with messages=get_flashed_messages(with_categories=true) %}{% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}<form method="post"><label>USERNAME / NIS</label><input name="username" required autofocus placeholder="Masukkan username atau NIS"><label>PASSWORD</label><input type="password" name="password" required placeholder="Masukkan password"><button class="btn">Masuk ke Sistem →</button></form><div style="margin-top:16px;padding-top:14px;border-top:1px solid #e7ecf4;text-align:center"><span class="muted" style="font-size:13px">Siswa belum punya akun?</span><br><a href="{{url_for('register_student')}}" class="btn secondary" style="margin-top:8px;width:100%">+ Daftar / Buat Akun Siswa</a></div><p class="notice" style="margin-top:14px">Jika akun sudah dibuatkan admin, gunakan <b>NIS</b> dan password awal <b>NIS@SMA</b>.</p></div></div>""")

@app.route('/daftar',methods=['GET','POST'])
def register_student():
    if session.get('uid'): return redirect(url_for('dashboard'))
    if request.method=='POST':
        nis=request.form.get('nis','').strip()
        nama=request.form.get('nama','').strip()
        kelas_id=request.form.get('kelas_id') or None
        jk=request.form.get('jk','').strip()
        no_hp=request.form.get('no_hp','').strip()
        pw=request.form.get('password','').strip()
        pw2=request.form.get('password_confirm','').strip()

        if not nis or not nama or not pw:
            flash('NIS, Nama Lengkap, dan Password wajib diisi.','danger')
        elif not nis.isdigit():
            flash('NIS harus berupa angka.','danger')
        elif len(pw)<8:
            flash('Password minimal 8 karakter.','danger')
        elif pw!=pw2:
            flash('Konfirmasi password tidak cocok.','danger')
        else:
            try:
                with db() as c:
                    existing_user=c.execute('SELECT * FROM users WHERE username=?',(nis,)).fetchone()
                    existing_siswa=c.execute('SELECT * FROM siswa WHERE TRIM(nis)=?',(nis,)).fetchone()

                    if existing_siswa:
                        linked=c.execute("SELECT * FROM users WHERE role='siswa' AND linked_id=?",(existing_siswa['id'],)).fetchone()
                        if linked and linked['wajib_ganti']==0:
                            flash('NIS ini sudah memiliki akun aktif. Silakan langsung login atau hubungi admin jika lupa password.','warning')
                            return redirect(url_for('login'))
                        # Jika data siswa sudah diinput admin tapi belum aktivasi password sendiri:
                        if kelas_id:
                            c.execute('UPDATE siswa SET nama=?,kelas_id=?,jk=COALESCE(NULLIF(?,""),jk),no_hp=COALESCE(NULLIF(?,""),no_hp) WHERE id=?',
                                      (nama,kelas_id,jk,no_hp,existing_siswa['id']))
                        if linked:
                            c.execute('UPDATE users SET username=?,nama=?,password=?,wajib_ganti=0,aktif=1 WHERE id=?',
                                      (nis,nama,generate_password_hash(pw),linked['id']))
                        else:
                            c.execute('INSERT INTO users(username,password,role,nama,linked_id,wajib_ganti,aktif) VALUES(?,?,?,?,?,0,1)',
                                      (nis,generate_password_hash(pw),'siswa',nama,existing_siswa['id']))
                    else:
                        if existing_user:
                            flash('NIS / Username sudah digunakan akun lain.','danger')
                            return redirect(url_for('register_student'))
                        cur=c.execute('INSERT INTO siswa(nis,nama,kelas_id,jk,no_hp) VALUES(?,?,?,?,?)',
                                      (nis,nama,kelas_id,jk,no_hp))
                        sid=cur.lastrowid
                        c.execute('INSERT INTO users(username,password,role,nama,linked_id,wajib_ganti,aktif) VALUES(?,?,?,?,?,0,1)',
                                  (nis,generate_password_hash(pw),'siswa',nama,sid))
                flash(f'Akun siswa untuk {nama} (NIS: {nis}) berhasil dibuat! Silakan login dengan password yang baru dibuat.','success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Terjadi duplikasi data NIS atau kelas tidak valid.','danger')
    with db() as c:
        kelas=c.execute('SELECT * FROM kelas ORDER BY nama').fetchall()
    return page('Daftar Akun Siswa',r"""<div class="login"><div class="loginbox" style="width:min(490px,100%)"><div style="font-size:12px;letter-spacing:2px;color:#4261e9;font-weight:800">PORTAL AKADEMIK · SMAMLA</div><h1>Buat Akun Siswa</h1><p class="muted">Daftarkan NIS Anda untuk membuat akun Portal Akademik</p>{% with messages=get_flashed_messages(with_categories=true) %}{% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}<form method="post"><label>NOMOR INDUK SISWA (NIS) *</label><input name="nis" required inputmode="numeric" placeholder="Contoh: 41246979"><label>NAMA LENGKAP *</label><input name="nama" required placeholder="Masukkan nama lengkap sesuai absen"><div class="formgrid"><div><label>KELAS</label><select name="kelas_id"><option value="">Pilih kelas</option>{% for k in kelas %}<option value="{{k.id}}">{{k.nama}}</option>{% endfor %}</select></div><div><label>JENIS KELAMIN</label><select name="jk"><option value="">Pilih</option><option>Laki-laki</option><option>Perempuan</option></select></div></div><label>NO. HP / WHATSAPP (OPSIONAL)</label><input name="no_hp" placeholder="Contoh: 08123456789"><div class="formgrid"><div><label>PASSWORD BARU (MIN. 8 KARAKTER) *</label><input type="password" name="password" minlength="8" required placeholder="Buat password"></div><div><label>ULANGI PASSWORD *</label><input type="password" name="password_confirm" minlength="8" required placeholder="Ketik ulang password"></div></div><button class="btn">Daftarkan Akun Saya →</button></form><div style="margin-top:14px;text-align:center"><a href="{{url_for('login')}}" class="muted" style="font-size:13px">← Kembali ke halaman Login</a></div></div></div>""",kelas=kelas)
@app.route('/logout')
@login_required
def logout(): session.clear(); return redirect(url_for('login'))
@app.route('/dashboard')
@login_required
def dashboard():
    with db() as c:
        stats={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['siswa','guru','kelas','mapel']}
        if session['role']=='siswa':
            sid=c.execute('SELECT linked_id FROM users WHERE id=?',(session['uid'],)).fetchone()['linked_id']
            if not sid: abort(403)
            recent=c.execute('SELECT * FROM presensi WHERE user_id=? ORDER BY tanggal DESC LIMIT 7',(session['uid'],)).fetchall()
            grade=c.execute('SELECT n.*,m.nama mapel,(n.nilai_uts+n.nilai_uas)/2 akhir FROM nilai n JOIN mapel m ON m.id=n.mapel_id WHERE n.siswa_id=? ORDER BY n.id DESC LIMIT 12',(sid,)).fetchall()
            fee=c.execute("SELECT * FROM keuangan WHERE siswa_id=? ORDER BY tanggal DESC",(sid,)).fetchall()
        else:
            recent=c.execute('SELECT * FROM presensi ORDER BY id DESC LIMIT 10').fetchall(); grade=[]; fee=[]
    return page('Dashboard',r"""<div class="grid">{% for k,v in stats.items() %}<div class="card"><div class="statlabel">{{k.upper()}}</div><div class="stat">{{v}}</div><div class="statlabel">Data terdaftar</div></div>{% endfor %}</div>
    {% if session.role in ['admin','guru'] %}
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
      <div><h3 style="margin:0 0 4px">Export Data Otomatis ke Excel (.xlsx)</h3><div class="muted" style="font-size:13px">Unduh rekap lengkap (Keuangan, Nilai, Presensi, Siswa, Guru, Mapel) dalam 1 file Excel otomatis.</div></div>
      <div class="actions">
        <a class="btn" href="{{url_for('export_excel', jenis='semua')}}">⬇ Download Semua Rekap (.xlsx)</a>
        <a class="btn secondary" href="{{url_for('reports')}}">Buka Pusat Laporan & Grafik</a>
      </div>
    </div>
    {% endif %}
    <div class="card"><h3>Aktivitas Presensi Terbaru</h3><div class="tablewrap"><table><tr><th>Nama</th><th>Tanggal</th><th>Waktu</th><th>Status</th></tr>{% for r in recent %}<tr><td>{{r.nama}}</td><td>{{r.tanggal}}</td><td>{{r.waktu}}</td><td><span class="tag">{{r.status}}</span></td></tr>{% else %}<tr><td colspan="4">Belum ada presensi.</td></tr>{% endfor %}</table></div></div>
    {% if session.role=='siswa' %}
    <div class="card"><h3>Grafik & Nilai Akademik Saya</h3>
      {% if grade %}
      <div style="height:260px;margin-bottom:18px"><canvas id="siswaGradeChart"></canvas></div>
      <script>
      new Chart(document.getElementById('siswaGradeChart'),{type:'bar',data:{labels:{{grade|map(attribute='mapel')|list|tojson}},datasets:[{label:'UTS',data:{{grade|map(attribute='nilai_uts')|list|tojson}},backgroundColor:'#5b7cfa',borderRadius:6},{label:'UAS',data:{{grade|map(attribute='nilai_uas')|list|tojson}},backgroundColor:'#19b7c9',borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true,max:100}}}});
      </script>
      {% endif %}
      <div class="tablewrap"><table><tr><th>Mapel</th><th>Semester</th><th>UTS</th><th>UAS</th><th>Rata-rata</th></tr>{% for n in grade %}<tr><td>{{n.mapel}}</td><td>{{n.semester}}</td><td>{{n.nilai_uts}}</td><td>{{n.nilai_uas}}</td><td><b>{{'%.2f'|format(n.akhir)}}</b></td></tr>{% else %}<tr><td colspan="5">Belum ada nilai.</td></tr>{% endfor %}</table></div>
    </div>
    <div class="card"><h3>Informasi Pembayaran</h3><div class="tablewrap"><table><tr><th>Tanggal</th><th>Jenis</th><th>Nominal</th><th>Status</th></tr>{% for f in fee %}<tr><td>{{f.tanggal}}</td><td>{{f.jenis}}</td><td>Rp {{'{:,.0f}'.format(f.nominal)}}</td><td><span class="tag">{{f.status}}</span></td></tr>{% else %}<tr><td colspan="4">Belum ada data pembayaran.</td></tr>{% endfor %}</table></div></div>
    {% endif %}""",stats=stats,recent=recent,grade=grade,fee=fee)

def admin(): return roles('admin')
@app.route('/siswa',methods=['GET','POST'])
@login_required
@roles('admin','guru')
def students():
    if request.method=='POST':
        if session['role']!='admin': abort(403)
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            sid=request.form.get('siswa_id')
            with db() as c:
                c.execute("DELETE FROM users WHERE role='siswa' AND linked_id=?",(sid,))
                c.execute('DELETE FROM siswa WHERE id=?',(sid,))
            log(f'Hapus data siswa ID {sid}')
            flash('Data siswa beserta akunnya berhasil dihapus.','success')
            return redirect(url_for('students'))
        if aksi=='reset':
            with db() as c:
                c.execute("DELETE FROM users WHERE role='siswa'")
                c.execute('DELETE FROM siswa')
                c.execute("DELETE FROM sqlite_sequence WHERE name='siswa'")
            log('Reset semua data siswa')
            flash('Seluruh data siswa (beserta nilai, keuangan, dan akun siswa terkait) berhasil direset!','success')
            return redirect(url_for('students'))
        nis=request.form.get('nis','').strip(); nama=request.form.get('nama','').strip(); kelas=request.form.get('kelas_id') or None
        if not nis or not nama: flash('NIS dan nama wajib diisi.','danger')
        else:
            try:
                with db() as c:
                    cur=c.execute('INSERT INTO siswa(nis,nama,kelas_id,jk,email,no_hp,alamat) VALUES(?,?,?,?,?,?,?)',(nis,nama,kelas,request.form.get('jk',''),request.form.get('email',''),request.form.get('no_hp',''),request.form.get('alamat','')))
                    sid=cur.lastrowid; temp=nis+'@SMA'
                    c.execute('INSERT INTO users(username,password,role,nama,linked_id,wajib_ganti) VALUES(?,?,?,?,?,1)',(nis,generate_password_hash(temp),'siswa',nama,sid))
                flash(f'Data siswa dan akun dibuat. Username: {nis} · Password sementara: {temp} (wajib diganti saat login).','success')
            except sqlite3.IntegrityError: flash('NIS sudah digunakan atau data kelas tidak valid.','danger')
        return redirect(url_for('students'))
    with db() as c:
        rows=c.execute('SELECT s.*,k.nama kelas FROM siswa s LEFT JOIN kelas k ON k.id=s.kelas_id ORDER BY s.nama').fetchall()
        kelas=c.execute('SELECT * FROM kelas ORDER BY nama').fetchall()
    return page('Data Siswa',r"""{% if session.role=='admin' %}<div class="card"><h3>Tambah Siswa + Buat Akun Otomatis</h3><form method="post"><div class="formgrid"><div><label>NIS (menjadi username)</label><input name="nis" required></div><div><label>Nama lengkap</label><input name="nama" required></div><div><label>Kelas</label><select name="kelas_id"><option value="">Pilih kelas</option>{% for k in kelas %}<option value="{{k.id}}">{{k.nama}}</option>{% endfor %}</select></div><div><label>Jenis kelamin</label><select name="jk"><option value="">Pilih</option><option>Laki-laki</option><option>Perempuan</option></select></div><div><label>Email</label><input name="email"></div><div><label>No. HP</label><input name="no_hp"></div></div><label>Alamat</label><textarea name="alamat"></textarea><button class="btn">Simpan Siswa & Buat Akun</button></form></div>{% endif %}<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Daftar Siswa · {{rows|length}} siswa</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) data siswa? Data nilai, keuangan, dan akun login siswa juga akan ikut terhapus!')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Data Siswa</button></form>{% endif %}</div><div class="tablewrap"><table><tr><th>NIS</th><th>Nama</th><th>Kelas</th><th>Jenis Kelamin</th><th>Akun</th>{% if session.role=='admin' %}<th>Aksi</th>{% endif %}</tr>{% for s in rows %}<tr><td>{{s.nis}}</td><td>{{s.nama}}</td><td>{{s.kelas or '-'}}</td><td>{{s.jk or '-'}}</td><td><span class="tag">Akun individual</span></td>{% if session.role=='admin' %}<td><form method="post" style="margin:0" onsubmit="return confirm('Hapus siswa {{s.nama}}?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="siswa_id" value="{{s.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="6">Belum ada data siswa.</td></tr>{% endfor %}</table></div></div>""",rows=rows,kelas=kelas)

@app.route('/akun',methods=['GET','POST'])
@login_required
@roles('admin')
def accounts():
    if request.method=='POST':
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            uid=request.form.get('uid')
            with db() as c:
                c.execute('DELETE FROM users WHERE id=? AND role="siswa"',(uid,))
            log(f'Hapus akun siswa ID {uid}')
            flash('Akun siswa berhasil dihapus.','success')
            return redirect(url_for('accounts'))
        if aksi=='reset_semua':
            with db() as c:
                c.execute('DELETE FROM users WHERE role="siswa"')
            log('Reset semua akun siswa')
            flash('Seluruh akun siswa berhasil direset/dihapus! (Akun admin tidak terhapus).','success')
            return redirect(url_for('accounts'))
        uid=request.form.get('uid'); new=request.form.get('password','')
        if len(new)<8: flash('Password minimal 8 karakter.','danger')
        else:
            with db() as c:
                c.execute('UPDATE users SET password=?,wajib_ganti=1 WHERE id=? AND role="siswa"',(generate_password_hash(new),uid))
            flash('Password akun siswa tersebut berhasil direset. Siswa wajib menggantinya saat login.','success')
        return redirect(url_for('accounts'))
    with db() as c:
        rows=c.execute("""SELECT u.id,u.username,u.nama,u.aktif,s.nis,s.nama siswa FROM users u LEFT JOIN siswa s ON s.id=u.linked_id WHERE u.role='siswa' ORDER BY u.nama""").fetchall()
    return page('Akun & Password Siswa',r"""<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:10px"><h3 style="margin:0">Manajemen Akun Individual</h3><form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) akun login siswa? Akun Admin tetap aman.')"><input type="hidden" name="aksi" value="reset_semua"><button class="btn danger">🗑 Reset Semua Akun Siswa</button></form></div><p class="muted">Setiap baris terhubung ke satu siswa. Reset password hanya mengubah akun yang dipilih.</p><div class="tablewrap"><table><tr><th>NIS / Username</th><th>Nama</th><th>Status</th><th>Reset Password</th><th>Hapus</th></tr>{% for u in rows %}<tr><td>{{u.username}}</td><td>{{u.siswa or u.nama}}</td><td>{{'Aktif' if u.aktif else 'Nonaktif'}}</td><td><form method="post" class="actions"><input type="hidden" name="uid" value="{{u.id}}"><input name="password" minlength="8" required placeholder="Password baru min. 8 karakter" style="max-width:220px;margin:0"><button class="btn secondary">Reset PW</button></form></td><td><form method="post" style="margin:0" onsubmit="return confirm('Hapus akun {{u.username}}?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="uid" value="{{u.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td></tr>{% else %}<tr><td colspan="5">Belum ada akun siswa.</td></tr>{% endfor %}</table></div></div>""",rows=rows)

@app.route('/password',methods=['GET','POST'])
@login_required
def change_password():
    if request.method=='POST':
        old=request.form.get('old',''); new=request.form.get('new','')
        with db() as c: u=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
        if not check_password_hash(u['password'],old): flash('Password lama tidak sesuai.','danger')
        elif len(new)<8: flash('Password baru minimal 8 karakter.','danger')
        elif new==old: flash('Password baru harus berbeda.','danger')
        else:
            with db() as c: c.execute('UPDATE users SET password=?,wajib_ganti=0 WHERE id=?',(generate_password_hash(new),session['uid']))
            flash('Password berhasil diperbarui.','success'); return redirect(url_for('dashboard'))
    return page('Ganti Password',r"""<div class="card" style="max-width:600px"><h3>Keamanan Akun</h3><form method="post"><label>Password saat ini</label><input type="password" name="old" required><label>Password baru (minimal 8 karakter)</label><input type="password" name="new" minlength="8" required><button class="btn">Simpan Password Baru</button></form></div>""")


@app.route('/absen',methods=['GET','POST'])
def public_attendance():
    """Link absensi publik: siswa memasukkan NIS tanpa perlu login portal."""
    student=None
    if request.method=='POST':
        nis=request.form.get('nis','').strip()
        pilihan=request.form.get('status','Hadir').strip()
        catatan=request.form.get('catatan','').strip()[:500]
        if not nis:
            flash('NIS wajib diisi.','danger')
        elif pilihan not in ('Hadir','Izin','Sakit'):
            flash('Pilihan status tidak valid.','danger')
        elif pilihan in ('Izin','Sakit') and not catatan:
            flash('Keterangan wajib diisi untuk status Izin atau Sakit.','danger')
        else:
            with db() as c:
                student=c.execute("""
                    SELECT s.id,s.nis,s.nama,k.nama AS kelas,u.id AS user_id
                    FROM siswa s
                    LEFT JOIN kelas k ON k.id=s.kelas_id
                    LEFT JOIN users u ON u.linked_id=s.id AND u.role='siswa' AND u.aktif=1
                    WHERE s.nis=?
                """,(nis,)).fetchone()
                if not student:
                    flash('NIS tidak ditemukan. Periksa kembali NIS atau hubungi admin sekolah.','danger')
                elif not student['user_id']:
                    flash('Akun siswa belum tersedia. Silakan hubungi admin sekolah.','danger')
                else:
                    now=datetime.now()
                    status='Terlambat' if pilihan=='Hadir' and now.strftime('%H:%M')>'07:15' else pilihan
                    try:
                        c.execute('INSERT INTO presensi(user_id,nama,role,tanggal,waktu,status,catatan) VALUES(?,?,?,?,?,?,?)',
                                  (student['user_id'],student['nama'],'siswa',now.date().isoformat(),now.strftime('%H:%M:%S'),status,catatan))
                        flash(f'Absensi berhasil dicatat. {student["nama"]} · {student["kelas"] or "Kelas belum diatur"} · {status}.','success')
                        student=None
                    except sqlite3.IntegrityError:
                        flash('NIS ini sudah melakukan absensi hari ini.','warning')
    return page('Absensi Siswa',r"""
    <div class="login"><div class="loginbox">
      <div style="font-size:12px;letter-spacing:2px;color:#4261e9;font-weight:800">PORTAL AKADEMIK · SMAMLA</div>
      <h1>Absensi Siswa</h1>
      <p class="muted">Masukkan NIS untuk mencatat kehadiran hari ini.</p>
      {% with messages=get_flashed_messages(with_categories=true) %}{% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}
      <form method="post">
        <label>NOMOR INDUK SISWA (NIS)</label>
        <input name="nis" required inputmode="numeric" autocomplete="off" placeholder="Masukkan NIS siswa" value="{{request.form.get('nis','')}}">
        <label>STATUS KEHADIRAN</label>
        <select name="status" required><option value="Hadir">Hadir</option><option value="Izin">Izin</option><option value="Sakit">Sakit</option></select>
        <label>KETERANGAN (WAJIB UNTUK IZIN/SAKIT)</label>
        <textarea name="catatan" maxlength="500" placeholder="Isi keterangan jika izin atau sakit"></textarea>
        <button class="btn">Kirim Absensi</button>
      </form>
      <p class="notice">Waktu absensi dicatat otomatis. Hadir setelah pukul 07.15 akan ditandai Terlambat. Absensi hanya dapat dilakukan satu kali per hari.</p>
    </div></div>
    """)

@app.route('/presensi',methods=['GET','POST'])
@login_required
def attendance():
    if request.method=='POST':
        if session.get('role') in ('admin','guru'):
            aksi=request.form.get('aksi')
            if aksi=='hapus':
                presensi_id=request.form.get('presensi_id')
                with db() as c:
                    c.execute('DELETE FROM presensi WHERE id=?',(presensi_id,))
                log(f'Hapus data presensi ID {presensi_id}')
                flash('Catatan presensi berhasil dihapus.','success')
                return redirect(url_for('attendance'))
            if aksi=='reset':
                if session.get('role')!='admin': abort(403)
                with db() as c:
                    c.execute('DELETE FROM presensi')
                    c.execute("DELETE FROM sqlite_sequence WHERE name='presensi'")
                log('Reset semua data presensi')
                flash('Seluruh riwayat presensi berhasil direset!','success')
                return redirect(url_for('attendance'))
            if aksi!='validasi': abort(403)
            try:
                presensi_id=int(request.form.get('presensi_id',''))
            except ValueError:
                abort(400)
            with db() as c:
                c.execute("UPDATE presensi SET validasi='Disetujui' WHERE id=? AND role='siswa'",(presensi_id,))
            flash('Absensi siswa berhasil divalidasi.','success')
            return redirect(url_for('attendance'))
        # Absensi mandiri hanya dapat dikirim oleh akun siswa yang terhubung
        # ke satu data siswa. Guru/admin hanya memantau dan memvalidasi.
        if session.get('role')!='siswa': abort(403)
        now=datetime.now(); uid=session['uid']; name=session['nama']
        with db() as c:
            linked=c.execute('SELECT linked_id FROM users WHERE id=? AND role=?',(uid,'siswa')).fetchone()
        if not linked or linked['linked_id'] is None: abort(403)
        pilihan=request.form.get('status','').strip()
        catatan=request.form.get('catatan','').strip()[:500]
        if pilihan not in ('Hadir','Izin','Sakit'):
            flash('Pilih status kehadiran yang tersedia.','danger')
            return redirect(url_for('attendance'))
        if pilihan in ('Izin','Sakit') and not catatan:
            flash('Keterangan wajib diisi untuk status Izin atau Sakit.','danger')
            return redirect(url_for('attendance'))
        # Status terlambat ditentukan otomatis hanya untuk siswa yang memilih Hadir.
        status='Terlambat' if pilihan=='Hadir' and now.strftime('%H:%M')>'07:15' else pilihan
        try:
            with db() as c:
                c.execute('INSERT INTO presensi(user_id,nama,role,tanggal,waktu,status,catatan) VALUES(?,?,?,?,?,?,?)',
                          (uid,name,'siswa',now.date().isoformat(),now.strftime('%H:%M:%S'),status,catatan))
            flash('Absensi mandiri berhasil dikirim.','success')
        except sqlite3.IntegrityError:
            flash('Akun ini sudah mengisi absensi hari ini. Absensi hanya dapat dikirim satu kali per hari.','warning')
        return redirect(url_for('attendance'))
    with db() as c:
        if session['role']=='siswa':
            rows=c.execute('SELECT * FROM presensi WHERE user_id=? ORDER BY tanggal DESC,waktu DESC',(session['uid'],)).fetchall()
            today=c.execute('SELECT * FROM presensi WHERE user_id=? AND tanggal=?',(session['uid'],date.today().isoformat())).fetchone()
            pres_stats=c.execute("SELECT status, COUNT(*) jumlah FROM presensi WHERE user_id=? GROUP BY status ORDER BY status",(session['uid'],)).fetchall()
        else:
            rows=c.execute('SELECT * FROM presensi ORDER BY tanggal DESC,waktu DESC LIMIT 300').fetchall()
            today=None
            pres_stats=c.execute("SELECT status, COUNT(*) jumlah FROM presensi GROUP BY status ORDER BY status").fetchall()
        total_pres=sum(p['jumlah'] for p in pres_stats) if pres_stats else 0
    return page('Presensi',r"""
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px">
        <h3 style="margin:0">Statistik & Persentase Kehadiran</h3>
        <a class="btn secondary" href="{{url_for('export_excel',jenis='absensi')}}">⬇ Export Excel Absensi (.xlsx)</a>
      </div>
      {% if pres_stats %}
      <div style="height:220px;max-width:380px;margin:0 auto 16px"><canvas id="attPieChart"></canvas></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;text-align:center;margin-bottom:10px">
        {% for p in pres_stats %}
        <div style="background:#f8faff;padding:12px;border-radius:12px;border:1px solid #e7ecf4">
          <div style="font-size:12px;color:#77829a;font-weight:700">{{p.status}}</div>
          <div style="font-size:20px;font-weight:800;color:#101b3d;margin:4px 0">{{p.jumlah}}</div>
          <div style="font-size:11px;color:#365cf5"><b>{{"%.1f"|format((p.jumlah / total_pres) * 100)}}%</b></div>
        </div>
        {% endfor %}
      </div>
      <script>
      new Chart(document.getElementById('attPieChart'),{
        type:'doughnut',
        data:{
          labels:{{pres_stats|map(attribute='status')|list|tojson}},
          datasets:[{data:{{pres_stats|map(attribute='jumlah')|list|tojson}},backgroundColor:['#10b981','#365cf5','#f59e0b','#ef4444'],borderWidth:0}]
        },
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}
      });
      </script>
      {% else %}
      <p class="muted">Belum ada data statistik kehadiran.</p>
      {% endif %}
    </div>
    {% if session.role=='siswa' %}<div class="card"><h3>Absensi Mandiri Siswa</h3><p class="muted">Isi kehadiran sendiri melalui akun pribadi. Absensi hanya dapat dikirim satu kali setiap hari.</p>{% if today %}<div class="flash success">Absensi hari ini sudah tercatat pada pukul {{today.waktu}} dengan status <b>{{today.status}}</b>.</div>{% else %}<form method="post"><label>Status kehadiran</label><select name="status" required><option value="">Pilih status kehadiran</option><option value="Hadir">Hadir</option><option value="Izin">Izin</option><option value="Sakit">Sakit</option></select><label>Keterangan (wajib untuk Izin/Sakit)</label><textarea name="catatan" maxlength="500" placeholder="Contoh: izin keperluan keluarga atau sakit"></textarea><button class="btn">Kirim Absensi Hari Ini</button></form><p class="notice">Jam pengiriman dicatat otomatis. Jika memilih Hadir setelah pukul 07.15, sistem menandai status Terlambat.</p>{% endif %}</div>{% else %}<div class="card"><h3>Pemantauan Absensi Siswa</h3><p class="muted">Guru dan admin dapat memantau catatan absensi siswa di bawah ini.</p><p><b>Link absensi untuk dibagikan ke siswa:</b></p><p><a class="btn" href="{{url_for('public_attendance')}}" target="_blank">Buka Halaman Absensi Siswa</a></p><p class="notice">Alamat link: {{request.host_url.rstrip('/')}}{{url_for('public_attendance')}} — bagikan alamat ini kepada siswa.</p></div>{% endif %}<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">{% if session.role=='siswa' %}Riwayat Absensi Saya{% else %}Rekap Absensi Siswa{% endif %}</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) data presensi?')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Presensi</button></form>{% endif %}</div><div class="tablewrap"><table><tr><th>Nama</th><th>Tanggal</th><th>Waktu</th><th>Status</th><th>Keterangan</th><th>Validasi</th>{% if session.role in ['admin','guru'] %}<th>Aksi</th>{% endif %}</tr>{% for r in rows %}<tr><td>{{r.nama}}</td><td>{{r.tanggal}}</td><td>{{r.waktu}}</td><td><span class="tag">{{r.status}}</span></td><td>{{r.catatan or '-'}}</td><td>{% if session.role in ['admin','guru'] and r.role=='siswa' and r.validasi!='Disetujui' %}<form method="post" style="margin:0"><input type="hidden" name="aksi" value="validasi"><input type="hidden" name="presensi_id" value="{{r.id}}"><button class="btn secondary">Validasi</button></form>{% else %}<span class="tag">{{r.validasi or 'Menunggu'}}</span>{% endif %}</td>{% if session.role in ['admin','guru'] %}<td><form method="post" style="margin:0" onsubmit="return confirm('Hapus catatan absensi {{r.nama}}?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="presensi_id" value="{{r.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="7">Belum ada data absensi.</td></tr>{% endfor %}</table></div></div>""",rows=rows,today=today)

def simple_master(title,table,fields,role='admin'):
    if request.method=='POST':
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            rid=request.form.get('row_id')
            with db() as c:
                c.execute(f'DELETE FROM {table} WHERE id=?',(rid,))
            log(f'Hapus data {table} ID {rid}')
            flash(f'Data {title} berhasil dihapus.','success')
            return redirect(request.path)
        if aksi=='reset':
            if session.get('role')!='admin': abort(403)
            with db() as c:
                c.execute(f'DELETE FROM {table}')
                c.execute('DELETE FROM sqlite_sequence WHERE name=?',(table,))
            log(f'Reset semua data {table}')
            flash(f'Seluruh {title} berhasil direset!','success')
            return redirect(request.path)
        vals=[]
        for f in fields:
            value=request.form.get(f,'').strip()
            # NIP and kode are optional identifiers; store blanks as NULL so multiple
            # teachers/subjects can be entered without unique-key collisions.
            if f in ('nip','kode') and not value:
                value=None
            vals.append(value)
        # Only the actual name is mandatory. Email and homeroom teacher are optional.
        name_index=fields.index('nama') if 'nama' in fields else 0
        if not vals[name_index]:
            flash('Nama wajib diisi.','danger')
        else:
            try:
                with db() as c:
                    c.execute(f"INSERT INTO {table}({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",vals)
                flash('Data berhasil ditambahkan.','success')
            except sqlite3.IntegrityError:
                flash('NIP, kode, atau nama kelas sudah digunakan. Periksa kembali data yang dimasukkan.','danger')
            except sqlite3.Error as e:
                flash(f'Gagal menyimpan data: {e}','danger')
        return redirect(request.path)
    with db() as c:
        rows=c.execute(f'SELECT * FROM {table} ORDER BY id DESC').fetchall()
    return page(title,r"""<div class="card"><h3>Tambah Data</h3><form method="post" class="actions">{% for f in fields %}<input name="{{f}}" placeholder="{{f.replace('_',' ').title()}}" {% if f=='nama' %}required{% endif %} style="max-width:260px">{% endfor %}<button class="btn">Tambah</button></form><p class="muted">Kolom Nama wajib diisi. Kolom lainnya boleh dikosongkan.</p></div><div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Daftar {{list_title}} · {{rows|length}} data</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) {{list_title}}?')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua {{list_title}}</button></form>{% endif %}</div><div class="tablewrap"><table><tr>{% for f in fields %}<th>{{f.replace('_',' ').title()}}</th>{% endfor %}<th>Aksi</th></tr>{% for r in rows %}<tr>{% for f in fields %}<td>{{r[f] or '-'}}</td>{% endfor %}<td><form method="post" style="margin:0" onsubmit="return confirm('Hapus data ini?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="row_id" value="{{r.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td></tr>{% else %}<tr><td colspan="{{fields|length + 1}}">Belum ada data.</td></tr>{% endfor %}</table></div></div>""",rows=rows,fields=fields,list_title=title)
@app.route('/guru',methods=['GET','POST'])
@login_required
@roles('admin','guru')
def teachers():
    if request.method=='POST':
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            gid=request.form.get('guru_id')
            with db() as c:
                c.execute('UPDATE jadwal SET guru_id=NULL WHERE guru_id=?',(gid,))
                c.execute('DELETE FROM guru WHERE id=?',(gid,))
            log(f'Hapus data guru ID {gid}')
            flash('Data guru berhasil dihapus.','success')
            return redirect(url_for('teachers'))
        if aksi=='reset':
            if session.get('role')!='admin': abort(403)
            with db() as c:
                c.execute('UPDATE jadwal SET guru_id=NULL')
                c.execute('DELETE FROM guru')
                c.execute("DELETE FROM sqlite_sequence WHERE name='guru'")
            log('Reset semua data guru')
            flash('Seluruh data guru berhasil direset!','success')
            return redirect(url_for('teachers'))
        nip=request.form.get('nip','').strip() or None
        nama=request.form.get('nama','').strip()
        email=request.form.get('email','').strip()
        no_hp=request.form.get('no_hp','').strip()
        if not nama: flash('Nama guru wajib diisi.','danger')
        else:
            try:
                with db() as c:
                    c.execute('INSERT INTO guru(nip,nama,email,no_hp) VALUES(?,?,?,?)',(nip,nama,email,no_hp))
                flash('Data guru berhasil ditambahkan.','success')
            except sqlite3.IntegrityError:
                flash('NIP sudah terdaftar.','danger')
        return redirect(url_for('teachers'))
    with db() as c:
        rows=c.execute('SELECT * FROM guru ORDER BY nama').fetchall()
    return page('Data Guru',r"""<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Tambah Data Guru</h3><a class="btn secondary" href="{{url_for('export_excel',jenis='guru')}}">⬇ Export Excel Guru (.xlsx)</a></div><form method="post" class="actions"><input name="nip" placeholder="NIP (opsional)" style="max-width:190px"><input name="nama" required placeholder="Nama Lengkap Guru *" style="max-width:250px"><input name="email" placeholder="Email (opsional)" style="max-width:210px"><input name="no_hp" placeholder="No. HP (opsional)" style="max-width:180px"><button class="btn">Tambah Guru</button></form></div><div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Daftar Guru · {{rows|length}} guru</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) data guru?')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Data Guru</button></form>{% endif %}</div><div class="tablewrap"><table><tr><th>NIP</th><th>Nama Guru</th><th>Email</th><th>No. HP</th><th>Aksi</th></tr>{% for r in rows %}<tr><td>{{r.nip or '-'}}</td><td>{{r.nama}}</td><td>{{r.email or '-'}}</td><td>{{r.no_hp or '-'}}</td><td><form method="post" style="margin:0" onsubmit="return confirm('Hapus data guru {{r.nama}}?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="guru_id" value="{{r.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td></tr>{% else %}<tr><td colspan="5">Belum ada data guru.</td></tr>{% endfor %}</table></div></div>""",rows=rows)

@app.route('/kelas',methods=['GET','POST'])
@login_required
@roles('admin','guru')
def classes(): return simple_master('Data Kelas','kelas',['nama','wali_kelas'])

@app.route('/mapel',methods=['GET','POST'])
@login_required
@roles('admin','guru')
def subjects():
    if request.method=='POST':
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            mid=request.form.get('mapel_id')
            with db() as c:
                c.execute('DELETE FROM jadwal WHERE mapel_id=?',(mid,))
                c.execute('DELETE FROM mapel WHERE id=?',(mid,))
            log(f'Hapus mata pelajaran ID {mid}')
            flash('Mata pelajaran berhasil dihapus.','success')
            return redirect(url_for('subjects'))
        if aksi=='reset':
            if session.get('role')!='admin': abort(403)
            with db() as c:
                c.execute('DELETE FROM jadwal')
                c.execute('DELETE FROM mapel')
                c.execute("DELETE FROM sqlite_sequence WHERE name='mapel'")
            log('Reset semua data mata pelajaran')
            flash('Seluruh mata pelajaran (beserta nilai & jadwal terkait) berhasil direset!','success')
            return redirect(url_for('subjects'))
        kode=request.form.get('kode','').strip() or None
        nama=request.form.get('nama','').strip()
        if not nama: flash('Nama mata pelajaran wajib diisi.','danger')
        else:
            try:
                with db() as c:
                    c.execute('INSERT INTO mapel(kode,nama) VALUES(?,?)',(kode,nama))
                flash('Mata pelajaran berhasil ditambahkan.','success')
            except sqlite3.IntegrityError:
                flash('Kode mata pelajaran sudah digunakan.','danger')
        return redirect(url_for('subjects'))
    with db() as c:
        rows=c.execute('SELECT * FROM mapel ORDER BY nama').fetchall()
    return page('Mata Pelajaran',r"""<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Tambah Mata Pelajaran</h3><a class="btn secondary" href="{{url_for('export_excel',jenis='mapel')}}">⬇ Export Excel Mapel (.xlsx)</a></div><form method="post" class="actions"><input name="kode" placeholder="Kode Mapel (opsional)" style="max-width:210px"><input name="nama" required placeholder="Nama Mata Pelajaran *" style="max-width:290px"><button class="btn">Tambah Mapel</button></form></div><div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Daftar Mata Pelajaran · {{rows|length}} mapel</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) mata pelajaran? Nilai dan jadwal terkait juga akan terhapus!')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Mapel</button></form>{% endif %}</div><div class="tablewrap"><table><tr><th>Kode</th><th>Nama Mata Pelajaran</th><th>Aksi</th></tr>{% for r in rows %}<tr><td>{{r.kode or '-'}}</td><td>{{r.nama}}</td><td><form method="post" style="margin:0" onsubmit="return confirm('Hapus mapel {{r.nama}}?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="mapel_id" value="{{r.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td></tr>{% else %}<tr><td colspan="3">Belum ada data mata pelajaran.</td></tr>{% endfor %}</table></div></div>""",rows=rows)

@app.route('/jadwal',methods=['GET','POST'])
@login_required
def schedule():
    if request.method=='POST':
        if session['role'] not in ['admin','guru']: abort(403)
        aksi = request.form.get('aksi')
        if aksi=='hapus':
            jid = request.form.get('jadwal_id')
            with db() as c:
                c.execute('DELETE FROM jadwal WHERE id=?',(jid,))
            log(f'Hapus jadwal ID {jid}')
            flash('Jadwal pelajaran berhasil dihapus.','success')
            return redirect(url_for('schedule'))
        if aksi=='reset':
            if session.get('role')!='admin': abort(403)
            with db() as c:
                c.execute('DELETE FROM jadwal')
                c.execute("DELETE FROM sqlite_sequence WHERE name='jadwal'")
            log('Reset semua jadwal pelajaran')
            flash('Seluruh jadwal pelajaran berhasil direset!','success')
            return redirect(url_for('schedule'))

        kelas_id = request.form.get('kelas_id')
        mapel_id = request.form.get('mapel_id')
        guru_id = request.form.get('guru_id') or None
        hari = request.form.get('hari')
        jam_mulai = request.form.get('jam_mulai')
        jam_selesai = request.form.get('jam_selesai')

        if not kelas_id or not mapel_id or not hari or not jam_mulai or not jam_selesai:
            flash('Kelas, Mapel, Hari, dan Jam wajib diisi dengan lengkap.','danger')
            return redirect(url_for('schedule'))

        try:
            with db() as c:
                c.execute('''
                    INSERT INTO jadwal(kelas_id, mapel_id, guru_id, hari, jam_mulai, jam_selesai) 
                    VALUES(?,?,?,?,?,?)
                ''', (kelas_id, mapel_id, guru_id, hari, jam_mulai, jam_selesai))
            flash('Jadwal pelajaran berhasil ditambahkan.','success')
        except Exception as e:
            flash(f'Gagal menyimpan jadwal: {e}','danger')
        return redirect(url_for('schedule'))

    with db() as c:
        rows=c.execute('SELECT j.*,k.nama kelas,m.nama mapel,g.nama guru FROM jadwal j LEFT JOIN kelas k ON k.id=j.kelas_id LEFT JOIN mapel m ON m.id=j.mapel_id LEFT JOIN guru g ON g.id=j.guru_id ORDER BY j.hari,j.jam_mulai').fetchall()
        kelas=c.execute('SELECT * FROM kelas ORDER BY nama').fetchall()
        mapel=c.execute('SELECT * FROM mapel ORDER BY nama').fetchall()
        guru=c.execute('SELECT * FROM guru ORDER BY nama').fetchall()
    return page('Jadwal Pelajaran',r"""{% if session.role in ['admin','guru'] %}<div class="card"><h3>Tambah Jadwal</h3><form method="post" class="formgrid"><div><label>Kelas</label><select name="kelas_id" required><option value="">Pilih Kelas</option>{% for x in kelas %}<option value="{{x.id}}">{{x.nama}}</option>{% endfor %}</select></div><div><label>Mapel</label><select name="mapel_id" required><option value="">Pilih Mapel</option>{% for x in mapel %}<option value="{{x.id}}">{{x.nama}}</option>{% endfor %}</select></div><div><label>Guru</label><select name="guru_id"><option value="">Belum ditentukan</option>{% for x in guru %}<option value="{{x.id}}">{{x.nama}}</option>{% endfor %}</select></div><div><label>Hari</label><select name="hari">{% for h in ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'] %}<option>{{h}}</option>{% endfor %}</select></div><div><label>Jam mulai</label><input type="time" name="jam_mulai" required></div><div><label>Jam selesai</label><input type="time" name="jam_selesai" required></div><button class="btn">Simpan Jadwal</button></form></div>{% endif %}<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Daftar Jadwal · {{rows|length}} jadwal</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) jadwal pelajaran?')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Jadwal</button></form>{% endif %}</div><div class="tablewrap"><table><tr><th>Hari</th><th>Jam</th><th>Kelas</th><th>Mapel</th><th>Guru</th>{% if session.role in ['admin','guru'] %}<th>Aksi</th>{% endif %}</tr>{% for r in rows %}<tr><td>{{r.hari}}</td><td>{{r.jam_mulai}} - {{r.jam_selesai}}</td><td>{{r.kelas}}</td><td>{{r.mapel}}</td><td>{{r.guru or '-'}}</td>{% if session.role in ['admin','guru'] %}<td><form method="post" style="margin:0" onsubmit="return confirm('Yakin ingin menghapus jadwal ini?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="jadwal_id" value="{{r.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="6">Belum ada jadwal pelajaran.</td></tr>{% endfor %}</table></div></div>""",rows=rows,kelas=kelas,mapel=mapel,guru=guru)

@app.route('/nilai',methods=['GET','POST'])
@login_required
@roles('admin','guru')
def grades():
    if request.method=='POST':
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            nid=request.form.get('nilai_id')
            with db() as c:
                c.execute('DELETE FROM nilai WHERE id=?',(nid,))
            log(f'Hapus data nilai ID {nid}')
            flash('Data nilai berhasil dihapus.','success')
            return redirect(url_for('grades'))
        if aksi=='reset':
            if session.get('role')!='admin': abort(403)
            with db() as c:
                c.execute('DELETE FROM nilai')
                c.execute("DELETE FROM sqlite_sequence WHERE name='nilai'")
            log('Reset semua data nilai')
            flash('Seluruh data nilai akademik berhasil direset!','success')
            return redirect(url_for('grades'))
        try:
            sid=int(request.form['siswa_id']); mid=int(request.form['mapel_id']); uts=float(request.form['uts']); uas=float(request.form['uas'])
            if not 0<=uts<=100 or not 0<=uas<=100: raise ValueError()
            with db() as c:
                c.execute("""INSERT INTO nilai(siswa_id,mapel_id,semester,tahun_ajaran,nilai_uts,nilai_uas,catatan) VALUES(?,?,?,?,?,?,?) ON CONFLICT(siswa_id,mapel_id,semester,tahun_ajaran) DO UPDATE SET nilai_uts=excluded.nilai_uts,nilai_uas=excluded.nilai_uas,catatan=excluded.catatan""",(sid,mid,request.form['semester'],request.form['tahun'],uts,uas,request.form.get('catatan','')))
            flash('Nilai tersimpan.','success')
        except Exception: flash('Periksa kembali data nilai.','danger')
        return redirect(url_for('grades'))
    with db() as c:
        siswa=c.execute('SELECT * FROM siswa ORDER BY nama').fetchall(); mapel=c.execute('SELECT * FROM mapel ORDER BY nama').fetchall()
        rows=c.execute('SELECT n.*,s.nis,s.nama siswa,m.nama mapel,(n.nilai_uts+n.nilai_uas)/2 akhir FROM nilai n JOIN siswa s ON s.id=n.siswa_id JOIN mapel m ON m.id=n.mapel_id ORDER BY n.id DESC').fetchall()
        chart_rows=c.execute('SELECT m.nama mapel, ROUND(AVG(n.nilai_uts),2) avg_uts, ROUND(AVG(n.nilai_uas),2) avg_uas, ROUND(AVG((n.nilai_uts+n.nilai_uas)/2),2) avg_akhir FROM nilai n JOIN mapel m ON m.id=n.mapel_id GROUP BY m.id, m.nama ORDER BY m.nama').fetchall()
    return page('Nilai Akademik',r"""
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px">
        <h3 style="margin:0">Grafik Rata-rata Nilai Akademik per Mata Pelajaran</h3>
        <a class="btn secondary" href="{{url_for('export_excel',jenis='nilai')}}">⬇ Export Excel Nilai (.xlsx)</a>
      </div>
      {% if chart_rows %}
      <div style="height:280px"><canvas id="nilaiChart"></canvas></div>
      <script>
      new Chart(document.getElementById('nilaiChart'),{
        type:'bar',
        data:{
          labels:{{chart_rows|map(attribute='mapel')|list|tojson}},
          datasets:[
            {label:'Rata-rata UTS',data:{{chart_rows|map(attribute='avg_uts')|list|tojson}},backgroundColor:'#5b7cfa',borderRadius:6},
            {label:'Rata-rata UAS',data:{{chart_rows|map(attribute='avg_uas')|list|tojson}},backgroundColor:'#19b7c9',borderRadius:6},
            {label:'Nilai Akhir',data:{{chart_rows|map(attribute='avg_akhir')|list|tojson}},backgroundColor:'#10b981',borderRadius:6}
          ]
        },
        options:{responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true,max:100}}}
      });
      </script>
      {% else %}
      <p class="muted">Belum ada data nilai untuk ditampilkan pada grafik. Tambahkan nilai di bawah ini.</p>
      {% endif %}
    </div>
    <div class="card"><h3>Input / Perbarui Nilai</h3><form method="post" class="formgrid"><div><label>Siswa</label><select name="siswa_id" required>{% for s in siswa %}<option value="{{s.id}}">{{s.nis}} · {{s.nama}}</option>{% endfor %}</select></div><div><label>Mata pelajaran</label><select name="mapel_id" required>{% for m in mapel %}<option value="{{m.id}}">{{m.nama}}</option>{% endfor %}</select></div><div><label>Semester</label><select name="semester"><option>Ganjil</option><option>Genap</option></select></div><div><label>Tahun ajaran</label><input name="tahun" placeholder="2026/2027" value="2026/2027" required></div><div><label>Nilai UTS</label><input name="uts" type="number" min="0" max="100" step=".01" required></div><div><label>Nilai UAS</label><input name="uas" type="number" min="0" max="100" step=".01" required></div></div><label>Catatan</label><input name="catatan"><button class="btn">Simpan Nilai</button></form></div>
    <div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Rekap Nilai · {{rows|length}} data</h3>{% if session.role=='admin' %}<form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) data nilai akademik?')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Nilai</button></form>{% endif %}</div><div class="tablewrap"><table><tr><th>NIS</th><th>Siswa</th><th>Mapel</th><th>Semester</th><th>Tahun</th><th>UTS</th><th>UAS</th><th>Rata-rata</th><th>Aksi</th></tr>{% for r in rows %}<tr><td>{{r.nis}}</td><td>{{r.siswa}}</td><td>{{r.mapel}}</td><td>{{r.semester}}</td><td>{{r.tahun_ajaran}}</td><td>{{r.nilai_uts}}</td><td>{{r.nilai_uas}}</td><td><b>{{'%.2f'|format(r.akhir)}}</b></td><td><form method="post" style="margin:0" onsubmit="return confirm('Hapus nilai {{r.siswa}} - {{r.mapel}}?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="nilai_id" value="{{r.id}}"><button class="btn danger" style="padding:6px 10px;font-size:11px">Hapus</button></form></td></tr>{% else %}<tr><td colspan="9">Belum ada data nilai.</td></tr>{% endfor %}</table></div></div>""",siswa=siswa,mapel=mapel,rows=rows,chart_rows=chart_rows)

@app.route('/keuangan',methods=['GET','POST'])
@login_required
@roles('admin')
def finance():
    if request.method=='POST':
        aksi=request.form.get('aksi')
        if aksi=='hapus':
            kid=request.form.get('keuangan_id')
            with db() as c:
                c.execute('DELETE FROM keuangan WHERE id=?',(kid,))
            log(f'Hapus transaksi keuangan ID {kid}')
            flash('Catatan transaksi keuangan berhasil dihapus.','success')
            return redirect(url_for('finance'))
        if aksi=='reset':
            with db() as c:
                c.execute('DELETE FROM keuangan')
                c.execute("DELETE FROM sqlite_sequence WHERE name='keuangan'")
            log('Reset semua data keuangan')
            flash('Seluruh data keuangan berhasil direset!','success')
            return redirect(url_for('finance'))
        with db() as c: c.execute('INSERT INTO keuangan(siswa_id,tanggal,jenis,nominal,status,keterangan) VALUES(?,?,?,?,?,?)',(request.form['siswa_id'],request.form.get('tanggal') or date.today().isoformat(),request.form['jenis'],int(request.form['nominal']),request.form['status'],request.form.get('keterangan','')))
        flash('Transaksi tersimpan.','success'); return redirect(url_for('finance'))
    with db() as c:
        siswa=c.execute('SELECT * FROM siswa ORDER BY nama').fetchall()
        rows=c.execute('SELECT k.*,s.nis,s.nama siswa FROM keuangan k JOIN siswa s ON s.id=k.siswa_id ORDER BY k.tanggal DESC, k.id DESC').fetchall()
        total_lunas=c.execute("SELECT COALESCE(SUM(nominal),0) FROM keuangan WHERE status='Lunas'").fetchone()[0]
        total_belum=c.execute("SELECT COALESCE(SUM(nominal),0) FROM keuangan WHERE status!='Lunas'").fetchone()[0]
        by_jenis=c.execute("SELECT jenis, SUM(CASE WHEN status='Lunas' THEN nominal ELSE 0 END) lunas, SUM(CASE WHEN status!='Lunas' THEN nominal ELSE 0 END) belum FROM keuangan GROUP BY jenis ORDER BY jenis").fetchall()
    return page('Keuangan Sekolah',r"""
    <div class="grid">
      <div class="card"><div class="statlabel">TOTAL LUNAS</div><div class="stat" style="color:#18764b">Rp {{'{:,.0f}'.format(total_lunas)}}</div><div class="statlabel">Dana sudah masuk</div></div>
      <div class="card"><div class="statlabel">BELUM LUNAS</div><div class="stat" style="color:#d23d4b">Rp {{'{:,.0f}'.format(total_belum)}}</div><div class="statlabel">Tagihan berjalan</div></div>
      <div class="card"><div class="statlabel">TOTAL TRANSAKSI</div><div class="stat">Rp {{'{:,.0f}'.format(total_lunas + total_belum)}}</div><div class="statlabel">{{rows|length}} catatan transaksi</div></div>
    </div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px">
        <h3 style="margin:0">Grafik Rekap Keuangan Sekolah</h3>
        <a class="btn secondary" href="{{url_for('export_excel',jenis='keuangan')}}">⬇ Export Excel Keuangan (.xlsx)</a>
      </div>
      {% if rows %}
      <div class="formgrid" style="align-items:center">
        <div style="height:260px"><canvas id="keuanganPieChart"></canvas></div>
        <div style="height:260px"><canvas id="keuanganBarChart"></canvas></div>
      </div>
      <script>
      new Chart(document.getElementById('keuanganPieChart'),{
        type:'doughnut',
        data:{
          labels:['Lunas (Rp)','Belum Lunas (Rp)'],
          datasets:[{data:[{{total_lunas}},{{total_belum}}],backgroundColor:['#10b981','#f43f5e'],borderWidth:0}]
        },
        options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Proporsi Status Pembayaran'}}}
      });
      new Chart(document.getElementById('keuanganBarChart'),{
        type:'bar',
        data:{
          labels:{{by_jenis|map(attribute='jenis')|list|tojson}},
          datasets:[
            {label:'Lunas',data:{{by_jenis|map(attribute='lunas')|list|tojson}},backgroundColor:'#10b981',borderRadius:6},
            {label:'Belum Lunas',data:{{by_jenis|map(attribute='belum')|list|tojson}},backgroundColor:'#f43f5e',borderRadius:6}
          ]
        },
        options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Rincian per Jenis Pembayaran'}}}
      });
      </script>
      {% else %}
      <p class="muted">Belum ada transaksi keuangan untuk ditampilkan pada grafik.</p>
      {% endif %}
    </div>
    <div class="card"><h3>Tambah Pembayaran</h3><form method="post" class="formgrid"><div><label>Siswa</label><select name="siswa_id" required>{% for s in siswa %}<option value="{{s.id}}">{{s.nis}} · {{s.nama}}</option>{% endfor %}</select></div><div><label>Tanggal</label><input type="date" name="tanggal"></div><div><label>Jenis pembayaran</label><input name="jenis" required placeholder="SPP / Daftar Ulang / Seragam"></div><div><label>Nominal (Rp)</label><input type="number" name="nominal" min="1" required></div><div><label>Status</label><select name="status"><option>Lunas</option><option>Belum Lunas</option></select></div><div><label>Keterangan</label><input name="keterangan"></div></div><button class="btn">Simpan Transaksi</button></form></div>
    <div class="card"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px"><h3 style="margin:0">Riwayat Pembayaran · {{rows|length}} transaksi</h3><form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN: Yakin ingin MERESET (hapus SEMUA) data keuangan sekolah?')"><input type="hidden" name="aksi" value="reset"><button class="btn danger">🗑 Reset Semua Data Keuangan</button></form></div><div class="tablewrap"><table style="font-size:12.5px"><tr><th style="padding:10px 8px">NIS</th><th style="padding:10px 8px">Siswa</th><th style="padding:10px 8px">Tanggal</th><th style="padding:10px 8px">Jenis</th><th style="padding:10px 8px">Nominal</th><th style="padding:10px 8px">Status</th><th style="padding:10px 8px">Keterangan</th><th style="padding:10px 8px">Aksi</th></tr>{% for r in rows %}<tr><td style="padding:10px 8px;white-space:nowrap">{{r.nis}}</td><td style="padding:10px 8px">{{r.siswa}}</td><td style="padding:10px 8px;white-space:nowrap">{{r.tanggal}}</td><td style="padding:10px 8px">{{r.jenis}}</td><td style="padding:10px 8px;white-space:nowrap">Rp {{'{:,.0f}'.format(r.nominal)}}</td><td style="padding:10px 8px;white-space:nowrap"><span class="tag">{{r.status}}</span></td><td style="padding:10px 8px">{{r.keterangan or '-'}}</td><td style="padding:10px 8px;white-space:nowrap"><form method="post" style="margin:0" onsubmit="return confirm('Hapus transaksi {{r.siswa}} ({{r.jenis}})?')"><input type="hidden" name="aksi" value="hapus"><input type="hidden" name="keuangan_id" value="{{r.id}}"><button class="btn danger" style="padding:5px 9px;font-size:11px">Hapus</button></form></td></tr>{% else %}<tr><td colspan="8">Belum ada data pembayaran.</td></tr>{% endfor %}</table></div></div>""",siswa=siswa,rows=rows,total_lunas=total_lunas,total_belum=total_belum,by_jenis=by_jenis)

@app.route('/laporan',methods=['GET','POST'])
@login_required
@roles('admin','guru')
def reports():
    if request.method=='POST':
        if session.get('role')!='admin': abort(403)
        if request.form.get('aksi')=='reset_all_master':
            with db() as c:
                c.executescript('''
                    DELETE FROM keuangan;
                    DELETE FROM nilai;
                    DELETE FROM jadwal;
                    DELETE FROM presensi;
                    DELETE FROM users WHERE role='siswa';
                    DELETE FROM siswa;
                    DELETE FROM guru;
                    DELETE FROM mapel;
                    DELETE FROM kelas;
                    DELETE FROM sqlite_sequence WHERE name IN ('keuangan','nilai','jadwal','presensi','siswa','guru','mapel','kelas');
                ''')
            log('RESET TOTAL SELURUH DATA SISTEM')
            flash('SELURUH data akademik (Siswa, Guru, Kelas, Mapel, Jadwal, Nilai, Presensi, Keuangan, Akun Siswa) berhasil direset bersih! Akun Admin tetap aktif.','success')
            return redirect(url_for('reports'))
    with db() as c:
        pres=c.execute('SELECT * FROM presensi ORDER BY tanggal DESC,waktu DESC LIMIT 300').fetchall()
        count=c.execute('SELECT COUNT(*) FROM presensi').fetchone()[0]
        pres_stats=c.execute("SELECT status, COUNT(*) jumlah FROM presensi GROUP BY status ORDER BY status").fetchall()
        nilai_stats=c.execute("SELECT m.nama mapel, ROUND(AVG((n.nilai_uts+n.nilai_uas)/2),2) rata FROM nilai n JOIN mapel m ON m.id=n.mapel_id GROUP BY m.id, m.nama ORDER BY m.nama").fetchall()
        total_lunas=c.execute("SELECT COALESCE(SUM(nominal),0) FROM keuangan WHERE status='Lunas'").fetchone()[0]
        total_belum=c.execute("SELECT COALESCE(SUM(nominal),0) FROM keuangan WHERE status!='Lunas'").fetchone()[0]
    return page('Laporan & Export Excel',r"""
    <div class="card">
      <h3>Export Otomatis ke Microsoft Excel (.xlsx)</h3>
      <p class="muted">Pilih data yang ingin diunduh otomatis dalam format Excel siap cetak & olah:</p>
      <div class="actions">
        <a class="btn" href="{{url_for('export_excel',jenis='semua')}}">⬇ Download Semua Data (Multi-Sheet .xlsx)</a>
        {% if session.role=='admin' %}<a class="btn secondary" href="{{url_for('export_excel',jenis='keuangan')}}">⬇ Excel Keuangan</a>{% endif %}
        <a class="btn secondary" href="{{url_for('export_excel',jenis='nilai')}}">⬇ Excel Nilai Akademik</a>
        <a class="btn secondary" href="{{url_for('export_excel',jenis='absensi')}}">⬇ Excel Absensi</a>
        <a class="btn secondary" href="{{url_for('export_excel',jenis='guru')}}">⬇ Excel Data Guru</a>
        <a class="btn secondary" href="{{url_for('export_excel',jenis='mapel')}}">⬇ Excel Mata Pelajaran</a>
      </div>
    </div>
    {% if session.role=='admin' %}
    <div class="card" style="border-color:#ffd6d9;background:#fffafa">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div>
          <h3 style="margin:0 0 4px;color:#a62e3a">Reset Total Semua Data (Persiapan Tahun Ajaran / Upgrade Data Baru)</h3>
          <div class="muted" style="font-size:13px">Menghapus sekaligus seluruh data <b>Siswa, Akun Siswa, Guru, Kelas, Mapel, Jadwal, Presensi, Nilai, dan Keuangan</b>. Akun Admin tetap aman.</div>
        </div>
        <form method="post" style="margin:0" onsubmit="return confirm('PERINGATAN KERAS: Anda akan menghapus SELURUH DATA di semua menu sekaligus! Pastikan sudah Export Excel terlebih dahulu. Lanjutkan?')">
          <input type="hidden" name="aksi" value="reset_all_master">
          <button class="btn danger" style="background:#d23d4b;color:#fff">⚠ Reset Total Semua Data Sistem</button>
        </form>
      </div>
    </div>
    {% endif %}
    <div class="card">
      <h3>Ringkasan Grafik Akademik, Absensi & Keuangan</h3>
      <div class="formgrid">
        <div style="height:250px"><canvas id="repPresChart"></canvas></div>
        <div style="height:250px"><canvas id="repNilaiChart"></canvas></div>
      </div>
      {% if session.role=='admin' %}
      <div style="height:240px;margin-top:18px"><canvas id="repKeuChart"></canvas></div>
      {% endif %}
      <script>
      new Chart(document.getElementById('repPresChart'),{
        type:'pie',
        data:{labels:{{pres_stats|map(attribute='status')|list|tojson}},datasets:[{data:{{pres_stats|map(attribute='jumlah')|list|tojson}},backgroundColor:['#10b981','#365cf5','#f59e0b','#ef4444']}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Statistik Kehadiran Siswa'}}}
      });
      new Chart(document.getElementById('repNilaiChart'),{
        type:'bar',
        data:{labels:{{nilai_stats|map(attribute='mapel')|list|tojson}},datasets:[{label:'Rata-rata Nilai Akhir',data:{{nilai_stats|map(attribute='rata')|list|tojson}},backgroundColor:'#365cf5',borderRadius:6}]},
        options:{responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true,max:100}},plugins:{title:{display:true,text:'Rata-rata Nilai per Mapel'}}}
      });
      {% if session.role=='admin' %}
      new Chart(document.getElementById('repKeuChart'),{
        type:'bar',
        data:{labels:['Lunas','Belum Lunas'],datasets:[{label:'Total Nominal (Rp)',data:[{{total_lunas}},{{total_belum}}],backgroundColor:['#10b981','#ef4444'],borderRadius:8}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Rekap Keuangan Sekolah (Rp)'}}}
      });
      {% endif %}
      </script>
    </div>
    <div class="card"><h3>Rekap Presensi · {{count}} catatan</h3><div class="tablewrap"><table><tr><th>Nama</th><th>Peran</th><th>Tanggal</th><th>Waktu</th><th>Status</th><th>Validasi</th><th>Catatan</th></tr>{% for r in pres %}<tr><td>{{r.nama}}</td><td>{{r.role}}</td><td>{{r.tanggal}}</td><td>{{r.waktu}}</td><td><span class="tag">{{r.status}}</span></td><td>{{r.validasi or 'Menunggu'}}</td><td>{{r.catatan or '-'}}</td></tr>{% else %}<tr><td colspan="7">Belum ada data presensi.</td></tr>{% endfor %}</table></div></div>""",pres=pres,count=count,pres_stats=pres_stats,nilai_stats=nilai_stats,total_lunas=total_lunas,total_belum=total_belum)

@app.route('/export/excel/<jenis>')
@login_required
@roles('admin','guru')
def export_excel(jenis):
    if jenis=='keuangan' and session.get('role')!='admin': abort(403)
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import BarChart, Reference
    except ImportError:
        flash('Library openpyxl belum terpasang. Jalankan: pip install openpyxl','danger')
        return redirect(url_for('reports'))

    wb=openpyxl.Workbook()
    wb.remove(wb.active)

    hdr_fill=PatternFill('solid',fgColor='172C60')
    hdr_font=Font(name='Calibri',size=11,bold=True,color='FFFFFF')
    zebra_fill=PatternFill('solid',fgColor='F4F7FC')
    thin_side=Side(style='thin',color='DCE3EF')
    border=Border(left=thin_side,right=thin_side,top=thin_side,bottom=thin_side)

    def add_sheet(title,headers,rows,money_cols=None,add_chart=False):
        money_cols=money_cols or []
        ws=wb.create_sheet(title=title[:31])
        ws.append(headers)
        for col_idx in range(1,len(headers)+1):
            cell=ws.cell(row=1,column=col_idx)
            cell.fill=hdr_fill
            cell.font=hdr_font
            cell.alignment=Alignment(horizontal='center',vertical='center')
            cell.border=border
        ws.row_dimensions[1].height=24

        for r_idx,row in enumerate(rows,start=2):
            ws.append(list(row))
            for c_idx in range(1,len(headers)+1):
                cell=ws.cell(row=r_idx,column=c_idx)
                cell.border=border
                if r_idx%2==1: cell.fill=zebra_fill
                if c_idx in money_cols:
                    cell.number_format='#,##0'
                    cell.alignment=Alignment(horizontal='right')

        for col_idx in range(1,len(headers)+1):
            col_letter=get_column_letter(col_idx)
            max_len=max((len(str(ws.cell(row=r,column=col_idx).value or '')) for r in range(1,len(rows)+2)),default=10)
            ws.column_dimensions[col_letter].width=min(max_len+5,42)
        ws.freeze_panes='A2'

        if add_chart and len(rows)>=2:
            try:
                chart=BarChart()
                chart.type='col'
                chart.style=10
                chart.title=f'Grafik {title}'
                chart.y_axis.title='Nilai / Nominal'
                data_ref=Reference(ws,min_col=len(headers),min_row=1,max_row=min(len(rows)+1,25))
                cats_ref=Reference(ws,min_col=2,min_row=2,max_row=min(len(rows)+1,25))
                chart.add_data(data_ref,titles_from_data=True)
                chart.set_categories(cats_ref)
                chart.width=18
                chart.height=10
                ws.add_chart(chart,f'{get_column_letter(len(headers)+2)}2')
            except Exception:
                pass

    with db() as c:
        if jenis in ('semua','keuangan') and session.get('role')=='admin':
            q=c.execute('SELECT k.tanggal, s.nis, s.nama, k.jenis, k.status, k.keterangan, k.nominal FROM keuangan k JOIN siswa s ON s.id=k.siswa_id ORDER BY k.tanggal DESC').fetchall()
            add_sheet('Rekap Keuangan',['Tanggal','NIS','Nama Siswa','Jenis Pembayaran','Status','Keterangan','Nominal (Rp)'],[tuple(r) for r in q],money_cols=[7],add_chart=True)

        if jenis in ('semua','nilai'):
            q=c.execute('SELECT s.nis, s.nama, m.nama, n.semester, n.tahun_ajaran, n.nilai_uts, n.nilai_uas, ROUND((n.nilai_uts+n.nilai_uas)/2,2) FROM nilai n JOIN siswa s ON s.id=n.siswa_id JOIN mapel m ON m.id=n.mapel_id ORDER BY s.nama, m.nama').fetchall()
            add_sheet('Nilai Akademik',['NIS','Nama Siswa','Mata Pelajaran','Semester','Tahun Ajaran','Nilai UTS','Nilai UAS','Rata-rata'],[tuple(r) for r in q],add_chart=True)

        if jenis in ('semua','absensi'):
            q=c.execute('SELECT p.tanggal, p.waktu, COALESCE(s.nis,"-"), p.nama, p.status, COALESCE(p.validasi,"Menunggu"), COALESCE(p.catatan,"-") FROM presensi p LEFT JOIN users u ON u.id=p.user_id LEFT JOIN siswa s ON s.id=u.linked_id ORDER BY p.tanggal DESC, p.waktu DESC').fetchall()
            add_sheet('Rekap Absensi',['Tanggal','Waktu','NIS','Nama Siswa','Status Kehadiran','Validasi','Keterangan'],[tuple(r) for r in q])

        if jenis in ('semua','mapel'):
            q=c.execute('SELECT id, COALESCE(kode,"-"), nama FROM mapel ORDER BY nama').fetchall()
            add_sheet('Mata Pelajaran',['ID','Kode Mapel','Nama Mata Pelajaran'],[tuple(r) for r in q])

        if jenis in ('semua','guru'):
            q=c.execute('SELECT id, COALESCE(nip,"-"), nama, COALESCE(email,"-"), COALESCE(no_hp,"-"), COALESCE(alamat,"-") FROM guru ORDER BY nama').fetchall()
            add_sheet('Data Guru',['ID','NIP','Nama Guru','Email','No. HP','Alamat'],[tuple(r) for r in q])

        if jenis=='semua':
            q=c.execute('SELECT s.nis, s.nama, COALESCE(k.nama,"-"), COALESCE(s.jk,"-"), COALESCE(s.no_hp,"-"), COALESCE(s.alamat,"-") FROM siswa s LEFT JOIN kelas k ON k.id=s.kelas_id ORDER BY s.nama').fetchall()
            add_sheet('Data Siswa',['NIS','Nama Siswa','Kelas','Jenis Kelamin','No. HP','Alamat'],[tuple(r) for r in q])

    if not wb.sheetnames:
        wb.create_sheet('Kosong').append(['Tidak ada data untuk diekspor'])

    buf=io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname=f'Rekap_SMAMLA_{jenis}_{date.today().isoformat()}.xlsx'
    return send_file(buf,as_attachment=True,download_name=fname,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.errorhandler(403)
def forbidden(e): return page('Akses Ditolak',"<div class='card'><h3>Akses tidak diizinkan</h3><p>Akun lu tidak memiliki hak untuk membuka halaman ini.</p></div>"),403
@app.errorhandler(404)
def missing(e): return page('Tidak Ditemukan',"<div class='card'><h3>Halaman tidak ditemukan.</h3></div>"),404

init_db()
if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000,debug=False)
