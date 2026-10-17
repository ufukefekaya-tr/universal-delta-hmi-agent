# Sayı alanlarının üç ayrı anlamı

Gözlem: Aynı sayının PLC'deki ham saklama, operatörün gördüğü ondalıklı metin ve vendor derleyicinin native giriş limiti üç farklı alandır. Tamsayı örneğine sadece nokta ekleyip giriş limitini aynı ham sayı bırakmak anlamı değiştirir. Native limitin exact decimal metni de binary çarpım/kesme nedeniyle bir eksilebilir.

Kök neden: Ortak ekran niyeti ile vendor compiler davranışının aynı doğrulama sayılması. Karşı görüş: Decimal/float ile ön kontrol yeterli olabilir; statik x87/CRT zinciri ve raw29/F2 örneği bunun genel garanti olmadığını gösterir.

Minimum değişiklik: Açık `integer_fixed_decimal` modeli; raw sınırlar/örnekler korunur, her nesne kendi F değerini taşır. Exact common yardımcıları ayrı tutulur. Kaynakla kalibre edilmiş UINT display F0–4 açılır; fractional input typed UNQUALIFIED kalır. Registered authority ve source/model/storage pins yeniden doğrulanır.

Tekrar test: `test_value_model.IntegerDecimalIntentTests`, `test_fixedpoint_native.FixedDecimalNativeTests`, `test_service.FixedDecimalServiceTests` ve actual SDK fixed display transaction. Browser shared tag/F1/F2, invalid/stale ve raw sınır senaryoları ayrıca kaydedilir. Generated dosyada yalnız digit alanları değişir; tüm target gövdesi restore/replay edilir.

Rollback: Yeni model alanını kaldırarak eski raw niyete dön; kaynakların üzerine yazılmaz. Kalibrasyon genişletme profili ayrı tutulur. Gösterge kabulünü input/compiler veya başka model/width kabulüne taşımama sınırı korunur. Vendor varlıkları bu dersle dağıtılmaz.
