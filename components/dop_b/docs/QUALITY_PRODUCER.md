# Değer güncelliği: araştırma ve uygulama sınırı

İki ayrı salt-okunur inceleme tamamlandı. **Güncellik üreticisi, maximum-age ve izin AND kalite birleşimi henüz desteklenmiş değildir.** [Birincil kaynaklar, adresler, hash’ler ve karşı senaryolar](../reports/QUALITY_PRODUCER_RESEARCH.json) kaydedildi. Bilgisayar kontrolü, vendor kodu çalıştırma, PLC işlemi ve native aday üretimi yapılmadı; mevcut 88 kaynak/826-test revision’ı değişmedi.

Başarısız haricî makro okuması eski hedef değeri koruyup −13 döndürebilir; makro devam eder. Sonraki koşulsuz geçerlilik veya zaman yazımı eski değeri güncel gösterir. GETLASTERROR örnek okumasından hemen sonra yakalanmalıdır. İncelenen makro yolunda başarı **1**’dir; bağlantı durumundaki 0 farklı bir sonuç alanıdır. Araya atama veya TIMETICK koymak önceki sonucu kaybettirir. Sonucu yakalayan yazımın kendi hatası da hesaba katılmalıdır.

COMLINKSTATUS yalnız kanalın son hatasını verir. Aynı kanaldaki başka başarılı okuma bu hatayı sıfırlayabilir; geçersiz kanal da 0 verir. NETLINKSTATUS bu emülatör binary’sinde sabit 0’dır. Bunlar belirli değerin geçerlilik veya yaş kaynağı olarak kullanılamaz.

TIMETICK bu emülatör yolunda yerel milisaniye sayacıdır. WORD 65,536 saniyede, DWORD yaklaşık 49,710 günde döner. Fiziksel panel eşdeğerliği, scheduler durması, yeniden başlatma ve epoch davranışı doğrulanmış değildir. Yeni bir tick, yeni PLC ölçümü anlamına gelmez. Callback/cache/transport/ölçüm sınırı tam kapanmadığından başarılı API okuması sonrasındaki zaman, yalnız dürüstçe tanımlanan yerel çağrı zamanı olabilir.

Kurulu HMC örnekleri GETLASTERROR framing’i gösterir; B10 producer donor’u sayılmaz. B10 tarafsız kaynaklarında dolu makro ve TIMETICK donor’u bulunamadı. Ortak REV writer ve bazı descriptor/width yolları statik olarak çözüldü; final operand işlemesi, getter/schedule sözleşmesi ve tam üretici kabulü açık kaldı. Mevcut source-local macro guard genişletilmedi.

Sonraki uygulama sözleşmesi şu kanıtları içermelidir:

- Kaynak/modelle bağlı getter, operand, bit genişliği, hedef bellek ve periyodik çalışma kaydı.
- Değer başına açık provenance: API çağrısı, transport tamamlanması ve PLC örnek zamanı birbirinden ayrılmalı.
- Başlangıçta unknown/izin 0; anında ve kontrol edilmiş sonuç yakalama; tutarlı değer/durum/zaman yayını.
- Producer dursa bile çalışan consumer expiry; wrap, yeniden başlatma ve epoch kontrolü.
- Başarısız okuma, araya komut girme, başka değerin başarısı, cached success, wrap/reset/stall ve tam BODY/replay/restoration testleri.

Bu kayıt uygulama kabulünün yerine geçmez. [Mevcut giriş izni](EXISTING_ENTRY_PERMISSION.md) yalnız saklanan giriş kontrolü kapsamındadır. Sürekli veya commit-time koruma, safety, vendor/panel çalışması ve tam V1 bu araştırmadan kapanmaz. Yeni exact writer scope ve bağımsız karşı inceleme olmadan native producer oluşturulmaz.

Genel ders: iletişim sağlığı, komut sonucu ve veri yaşı farklı şeylerdir. Minimum düzeltme önce doğru provenance ve hata alanını tanımlamaktır; tahmini bir makro eklemek değildir. Kaynak kod değişmediğinden rollback araştırma belgelerini geri almakla sınırlıdır.
