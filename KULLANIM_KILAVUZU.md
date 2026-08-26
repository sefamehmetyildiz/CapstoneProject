# Biomech Analyzer — Kullanım Kılavuzu (Türkçe)

Bu yazılım, tek bacak sıçrama testlerinden toplanan kuvvet platformu (CSV),
sEMG/Delsys (MAT veya CSV) ve Xsens (MVNX) verilerini otomatik olarak analiz
eder ve her katılımcı için İngilizce bir PDF risk raporu üretir.

> **Önemli:** Tüm çıktılar yalnızca **karar-destek** amaçlıdır; tıbbi tanı
> değildir ve klinisyen değerlendirmesinin yerine geçmez.

---

## 1. Program nasıl açılır?

### En kolay yol
Proje klasöründeki **`BiomechAnalyzer-Baslat.bat`** dosyasına çift tıklayın.
Paketlenmiş uygulama (`dist\BiomechAnalyzer\BiomechAnalyzer.exe`) varsa onu,
yoksa Python ortamını kullanarak arayüzü açar.

### İlk kurulum (sadece bir kez, geliştirici bilgisayarında)
```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### Başka bir bilgisayara kurulum
`dist\BiomechAnalyzer\` klasörünü olduğu gibi kopyalayın ve içindeki
`BiomechAnalyzer.exe`'yi çalıştırın. Python kurulumu gerekmez.

---

## 2. Veri nasıl eklenir?

Her katılımcı için **tek bir klasör** oluşturun. Mevcut `SubjectsData`
düzeni desteklenir:

```
SubjectsData/
  subject 1 .../
    force plate/          <- Bertec CSV dosyaları (Fx, Fy, Fz, COP...)
      slvjbaseline.csv
      sldjcognitive.csv
      ...
    converted/            <- Delsys MAT/CSV + Xsens MVNX dosyaları
      slvjbaseline.mat    (veya slvjbaseline.csv = Delsys EMG export'u)
      slvjbaseline.mvnx
      ...
    original/             <- Ham .hpf/.mvn dosyaları (yazılım bunları atlar)
```

### Dosya adlandırma
Dosya adında **görev** ve **koşul** geçmelidir (büyük/küçük harf fark etmez,
bitişik yazım kabul edilir):

| Ne | Kabul edilen yazımlar |
|---|---|
| Görev | `slvj`, `vertical` — `sldj`, `drop` |
| Koşul | `baseline`, `correct`, `corect`, `natural` — `upright` — `cognitive`, `dualtask` |

Örnekler: `slvjbaseline.csv`, `SLDJ_cognitive.mat`, `sldjupright-002.mvnx`,
`SLVJ_corect.csv` — hepsi tanınır.

### Gizlilik (KVKK)
Klasör adlarına **gerçek isim yazmayın**. `subject 4 sefa` gibi bir klasör
otomatik olarak `S04` anonim kimliğine çevrilir ve uyarı gösterilir; ama en
doğrusu klasörü baştan `S04` gibi adlandırmaktır. Raporlarda ve veritabanında
yalnızca anonim kimlik kullanılır.

---

## 3. Analiz ve çıktı nasıl alınır? (Masaüstü uygulaması)

1. **1. Folder Selection** sekmesinde:
   - Anonim kimliği yazın (boş bırakılırsa klasör adından türetilir),
   - **Select Folder…** ile katılımcı klasörünü seçin,
   - (İsteğe bağlı) BME ekibinin normatif **baseline** dosyasını seçin,
   - **Validate Files**'a basın. Ağaçta 6 deneme ve dosya durumları görünür.
2. **2. Analysis Dashboard** sekmesinde **Run Analysis**'e basın.
   İlerleme ve uyarılar günlükte listelenir (eksik dosyalar atlanır, analiz
   durmaz).
3. **3. Results and Report** sekmesinde:
   - *Trial summary*: deneme başına özet,
   - *Features*: çıkarılan tüm özellikler (baseline z-skorlarıyla),
   - *Risk indicators*: tetiklenen göstergeler,
   - *Feature plots*: bir deneme satırı seçince kuvvet eğrisi önizlemesi.
   - **Generate PDF Report** → PDF `output\reports\` klasörüne yazılır ve
     açmak isteyip istemediğiniz sorulur.
   - "Save results to local SQLite database" işaretlenirse sonuçlar
     `output\results.sqlite3` dosyasına da kaydedilir.

### Gelişmiş ayarlar
**Advanced / Research** sekmesinden filtre kesim frekansı, temas eşiği (Fz),
EMG RMS penceresi değiştirilebilir; Research Mode ile makine öğrenmesi modeli
eğitilebilir (yalnızca proje ekibi için, keşifsel).

---

## 4. Komut satırından toplu işlem

Tek katılımcı:
```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m biomech_analyzer.cli validate "SubjectsData\subject 1 zeynep"
.\.venv\Scripts\python -m biomech_analyzer.cli report   "SubjectsData\subject 1 zeynep"
```

**Tüm katılımcılar tek komutla:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\analyze_all_subjects.ps1
```
Raporlar `output\reports\` klasöründe toplanır (örn. `S01_biomech_report.pdf`).

---

## 5. Sık karşılaşılan durumlar

| Mesaj | Anlamı ve çözümü |
|---|---|
| "contains only synchronization channels (Sync, Aux)" | Bertec export'unda kuvvet kanalları seçilmemiş. **Kayıt Bertec yazılımından Fx/Fy/Fz kanallarıyla yeniden export edilmeli.** (Gerçek veride S09–S12 ve S15'te görüldü.) |
| "Unloaded-plate offset ... removed" | Platform kayıttan önce sıfırlanmamış (boş platform ~40 N okuyor). Yazılım otomatik düzeltir; bilgi amaçlıdır. |
| "N jump repetitions detected" | Kayıtta birden çok sıçrama tekrarı var. Varsayılan olarak **en uzun uçuş süreli** tekrar analiz edilir (BME onayı bekleyen kural). |
| "No MVIC normalization values found" | MVIC verisi export'ta yok; EMG genlikleri normalize edilmeden (ham birimle) raporlanır. |
| "EMG recording covers only part of the force-plate session" | Cihaz kayıtları ayrı başlatılmış; çapraz-zaman hizalaması yaklaşıktır. Gelecek ölçümlerde donanımsal tetik (trigger) önerilir. |
| "Could not assign '...' to a trial" | Dosya adında görev/koşul anahtar kelimesi yok (örn. `Run_number_...csv`). Dosyayı §2'deki kurala göre yeniden adlandırın. |
| "Expected trial ... was not found" | O deneme için dosya eksik. Analiz kalan denemelerle devam eder. |

## 6. Gerçek veri seti mevcut durumu (26.08.2026 taraması)

| Denek | Durum |
|---|---|
| S01–S08 | 6/6 deneme tam analiz ediliyor |
| S09 | SLVJ tamam; SLDJ kuvvet dosyaları yalnızca Sync/Aux (yeniden export gerekli) |
| S10, S11, S12, S15 | Tüm kuvvet dosyaları yalnızca Sync/Aux (yeniden export gerekli) |
| S13 | EMG/Xsens dönüştürülmemiş; kuvvet analizi 5/5 çalışıyor |
| S14, S16 | Veriler büyük ölçüde dönüştürülmemiş (.hpf/.mvn); yalnızca 1'er deneme mevcut |
