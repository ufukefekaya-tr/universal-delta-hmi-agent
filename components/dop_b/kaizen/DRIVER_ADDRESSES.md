# Adres sözleşmesi ve hata kapısı dersleri

Gözlem: captured M0/D0 alt kümesi gerçek programın ayrı kontrollerini temsil etmiyordu. Driver kaynakları ve manufacturer serial DVP dokümanı M/S/D için daha geniş decimal bölgeleri destekledi; native Link/MemType ile DLL device kodlarının ayrı anlamları vardı.

Minimum değişiklik: kaynak driver span SHA, registered factual authority ve tip/bölge aralığına bağlı optional namespace. Kontrolün width/format, kanal/istasyon ve yetkili tag hakkı korunur. Başka driver, CPU veya veri tipine genellenmez. Rollback: eski source_controls_v1 profili namespace olmadan captured M0/D0 davranışını sürdürür; önceki kaynak byte'ları değişmez.

N1 — Tetikleyici: geçerli boyuttaki JSON içinde 500-deep list veya cyclic doğrudan Python girdisi. Kanıt: denetmen namespace constructor/profile copy yolunda raw RecursionError üretti. Etki: güvenilir typed reject yerine beklenmeyen exception; kabul bypass kanıtı yok. Düzeltme: native tip kontrolünü deepcopy önüne almak, shared JSON decoder recursion/depth64/nodes250000 kapısı. Tekrar test: public open, iki helper, decoder, breadth ve isolation senaryoları typed hata; oturum/çıktı yok.

N2 — Tetikleyici: ilk okuma sonrası authority dosyasının save freshness callback'inde kaybolması veya erişilemez olması. Kanıt: iki helper FileNotFoundError/PermissionError/generic OSError veriyordu. Etki: hata tanısı tutarsız; kayıt kabulü yapılmıyordu. Düzeltme: bounded dependency open sırasında OSError → CALIBRATION_CHANGED. Tekrar test: gerçek temporary-save cleanup regresyonu ve bağımsız altı hata senaryosu; accepted çıktı yok.

Karşı görüş: hash eşitliği tek başına driver/width/address semantiği kanıtı değildir. Native baseline, bağımsız tam gövde beklentisi, readonly yetkisi ve range testleri birlikte gerekir. Boş veya atlanan test PASS değildir. Aynı prefix'li M1/M10 adresleri exact eşleştirilir; substring patch kullanılmaz. [Exact kabul](../reports/DRIVER_ADDRESS_MILESTONE.json).
