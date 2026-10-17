# Aile izolasyonu

Ortak katman native byte veya vendor enum düzenlemez. MCP çağrısını açık aile önekiyle ayrı kurulu backend'e gönderir. DOP-B modülü `universal_hmi.cli`, DIAScreen hedef sözleşmesi `universal_diascreen_hmi.cli`dir. Aile profili ve dosya uzantısı ön kontroldür; gerçek native içerik, model ve sürüm denetimini backend yapar.

Her aile için dört ayrık kök gerekir: immutable kurulum, workspace, profile registry, state. Bunlar birbirinin altı olamaz. İki ailenin kökleri de çakışamaz. Symlink/junction reddedilir. Python çalıştırılabilir dosyası, venv ve temel Python çalışma ortamının tamamı (bytecode, import hook ve bağımlılıklar dahil) ile profil ağacı hash ile sabitlenir; çağrı öncesi/sonrası yeniden doğrulanır. Yapılandırma ve pin dosyaları mutable workspace/state dışında kalır.

Bu ayrım aynı OS kullanıcısıyla çalışan süreçlerde hata/kapsam izolasyonudur, kötü niyetli backend'e karşı OS sandbox değildir. Güvenilmeyen yürütülebilir kod kaydedilmez. Bağımlılıklar kurulumda kilitle doğrulanır; yerel Python import köklerindeki tüm dosyalar her çağrıda yeniden doğrulanır. İşletim sisteminin dış DLL dosyaları bu envantere dahil değildir; bu kontrol bir OS sandbox veya bütün sistem doğrulaması değildir.

Oturum ve plan kimlikleri gateway'in aile + backend süreç nesli + kimlik türü tablosundan rastgele dış kimliğe çevrilir. Diğer aileye, farklı tür alanına veya yeniden başlatılmış oturuma ait kimlik reddedilir. Yalnız protokolün üst seviye kimlik alanları çevrilir; tag adresleri ve tasarım metinleri değiştirilmez. Planın oturuma ait olup olmadığını native backend ayrıca kontrol eder.

Süreç arızası diğer aileyi kapatmaz. Native kaynak ve candidate yetkisi backend'e aittir. Gateway timed-out mutasyon sonucunu başarıya çeviremez: kullanıcı yeni oturumda çıktı/diff'i incelemelidir; mevcut dosya üzerine yazılmaz. RAM oturumları kalıcı iş kuyruğu değildir. DOP-B kalıcı job runner'ı ayrı sürümde korunur.

## Taşıma

Repo ve dağıtım dosyalarında eski host yolu bulunmaz. `.local/gateway.json` yolları bulunduğu klasöre göredir; bu dosya yerel kurulum sırasında oluşur. Sanal ortamlar başka bilgisayara kopyalanmaz; temiz paketteki kurulum tekrar çalıştırılır. Profil/driver/source yetkileri özel proje girdisi olarak ayrıca taşınır; müşteri native dosyası genel dağıtıma eklenmez.

## Bağımlılık sınırları

DOP-B'nin pinli özgün kaynak sürümü ayrı arşiv olarak dağıtılır; içeriği DIAScreen paketine kopyalanmaz. Tarihsel upstream DIAScreen kodunun lisansı belirtilmediği için yeni dağıtımda yoktur. Bağımsız DIAScreen ajanı aynı davranışları özgün olarak geliştirir. Tarihsel kaynak envanteri, yeni uygulamanın tamamlandığına dair kanıt değildir.

## Doğrulama maliyeti

Her çağrı öncesi/sonrası tüm Python import kökleri yeniden okunur. Bu Windows kurulumunda 6.619 dosyalı envanter için tek doğrulama yaklaşık 13 saniye ölçüldü; disk ve güvenlik yazılımına göre değişir. Çağrı gecikmesi bu maliyeti içerir. Doğrulama atlanarak veya yalnız dosya zamanına güvenilerek hızlandırılmaz.
