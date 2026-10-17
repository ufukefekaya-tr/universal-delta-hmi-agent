# Universal Delta HMI Agent

Delta HMI projeleri için ortak ajan girişi; DOP-B ve DOP-100/DIAScreen üreticileri ayrı repo, süreç, kurulum, profil ve çalışma alanında kalır.

**Durum: ortak çatının test edilmiş ara sürümü; iki ailenin birleşik teslimi henüz tamamlanmadı.** DOP-B 0.2.0 ayrı kurulumdan gerçek stdio üzerinden bağlandı. DIAScreen'in tarihsel araçları bağımsız `universal-diascreen-hmi-agent` deposuna dönüştürülüyor. O teslim doğrulanana kadar `dop_100` kapalıdır. Başka adaptöre otomatik yönlendirme yoktur.

## Başlatma

Temiz çevrimdışı paketi yeni bir klasöre çıkarın. Windows x64:

```powershell
./scripts/bootstrap.ps1
./.venv/Scripts/python.exe -m delta_hmi.cli config --config .local/gateway.json
```

İkinci komut, o bilgisayar için MCP bağlantı ayarını üretir; istemci ayarlarını değiştirmez. MCP komutu `delta-hmi serve --config <üretilen yapılandırma>` olur. `doctor` yapılandırma/hash durumunu gösterir; DIAScreen eksik olduğu sürece çıkış kodu 2 verir.

Kaynak checkout'ta paket arşivi yoksa `bootstrap.ps1 -BackendArchive <kilitli DOP-B arşivi>` kullanılır. Arşiv SHA'sı `templates/releases.lock.json` ile eşleşmelidir. Sıfırdan Python kurulumu DOP-B'nin paketlenmiş, hash doğrulamalı çalışma ortamını kullanır. Yönetici yetkisi veya vendor IDE gerekmez. Linux x86_64 giriş betiği `sh scripts/bootstrap.sh <arşiv>`; bu yeni çatının Linux kurulum kabulü henüz yapılmadı. Windows kurulum kabulü mevcut kullanıcıda temiz proje ortamındadır, yeni OS/VM değildir.

## Araçlar

`delta_catalog`, ailelerin gerçek kullanılabilirliğini bildirir. `dop_b__` önekiyle `open_project`, `capabilities`, `inspect`, `plan_changes`, `preview`, `validate`, `apply_plan`, `save_as`, `diff` sunulur. DOP-100 kendi backend'i ve araç sözleşmesi doğrulanınca `dop_100__` alanından sunulacaktır.

Mevcut DOP-B'nin beş kalıcı headless iş aracı kendi sürümünde korunur. Bu çatı sürümü yalnız dokuz dosya aracını yönlendirir; job-policy bağlayıp sırf araç keşfi sırasında eski görevleri başlatmaz. Kalıcı iş entegrasyonu ayrı kabul kapısıdır; özellik silinmiş veya ortak çatıda uygulanmış sayılmaz.

Yeni kullanıcı projesinde profil, kaynak, adres ve davranış sözleşmesi seçilir; önizleme/onay/native üretim akışı backend'in kapılarından geçer. Bu repo ekran tasarımı veya PLC programı içermez. Sentetik testler vendor/panel kabulü değildir.

- [Workflow](docs/WORKFLOW.md) ve [goals](docs/GOALS.md)
- [Mimari ve izolasyon](docs/ARCHITECTURE.md)
- [Eksiksiz özellik aktarım listesi](docs/FEATURE_MIGRATION.json)
- [Yeni ajanın başlangıcı](docs/AGENT_START.md)
- [DIAScreen teslim sözleşmesi](docs/DIASCREEN_HANDOFF.md)

`full Delta family` burada ortak organizasyon hedefidir; bütün Delta modellerinin, sürücülerinin veya özelliklerinin doğrulanmış desteği anlamına gelmez.

Test ve inceleme kayıtları: [doğrulama](reports/VERIFICATION.json), [bağımsız teknik inceleme](reports/INDEPENDENT_REVIEW.json), [açık aktarım kabulü](reports/OMISSION_STATUS.md).
