# Gözlem: native kopya ile mantıksal kontrol tanımı ayrılmalı

DIAScreen sayısal giriş donörünün ReadVar alanı `None`, ReadMemType alanı `3` iken WriteVar `$120`'dir. Ortak numeric_input modeli aynı mantıksal process tagının açık read/write bağlarını ister. Donörü bu modele doğrudan aktarmak, henüz doğrulanmamış bir native okuma semantiğini uydururdu.

Kök neden, stored object copy ile logical process/control qualification'ın tek kabul etiketiyle anlatılmasıdır. Karşı inceleme; shared source adreslerini, etkin eski makroları, momentary efekt metadata'sını ve küçük yardımcı pencerenin ayrı Doc/Panel ölçülerini de ortaya çıkardı.

Minimum düzeltme: ayrı `native_control_clone` intent'i ve kaynak sabitlenmiş adapter. Yalnız ID/geometri/buton primary caption'ları değişir; raw native bağlar ve bütün diğer metadata korunur. Preview bilinmeyen native placeholder'dır; ordinary control capability, sample veya runtime durumu üretilmez.

Testler source/review freshness, original BODY restoration, raw insertion oracle, kayıt/yeniden okuma, replay/no-op ve tür/adres/stil/makro/state-frame sapmalarını kapsamalıdır. Güncel test/kabul sonucu VERIFICATION kaydına bağlıdır; bu Kaizen bir PASS belgesi değildir.

Rollback ayrı yeni dosyanın terk edilmesidir; kaynak değişmez. Genellenebilir ders, görünür kontrolün logical process binding'ini source record key'lerinden tahmin etmemektir. Bu exact DIAScreen sürüm/donör sözleşmesi bütün aileye veya başka vendor'a genellenmez.

Tam regresyonda ayrı clone türünün eklenmesi üç eski exact test beklentisini eskitti. İlk880 root/bağımsız turu FAIL olarak korundu. Üç predicate/exclusion satırı güncellenirken önceki UNKNOWN/no-sample ve diğer-kind olumsuz kontroller aynen korundu; runtime/native/helper kodu değişmedi. Yeni tam tekrarın kabulü milestone'a bağlıdır. Yeni opak tür eklemek, eski türe özel test sözleşmelerinin de birlikte incelenmesini gerektirir; test başarısızlığını atlamak veya daha gevşek assertion ile gizlemek kabul edilmez.
