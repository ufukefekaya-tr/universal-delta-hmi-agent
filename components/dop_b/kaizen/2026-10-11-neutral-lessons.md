# Neutral başlangıç dersleri — 2026-10-11

Kaynak: başlangıç mühendislik risk analizi. Bu kayıt gerçek müşteri dosyası taşımaz ve tamamlanmış vendor/panel testi iddiası değildir.

| Gözlem | Kök neden | Karşı görüş | Minimum değişiklik | Test / rollback / sınır |
|---|---|---|---|---|
| Daha az kelime talebi bütün ekranları aynı görünüme düzleyebilir. | Metin yoğunluğu ile state/hierarchy ayrımını aynı ölçü sanmak. | Tutarlı görsel dil öğrenmeyi kolaylaştırır; ayrımın tamamını kaldırmak gerekmez. | Gereksiz yazıyı azalt; alarm/normal/disabled/unknown ve action/feedback ayrımını koru. | Test: ordered iki estetik reviewer aynı sürümlü preview'da ayrımları inceler. Rollback: önceki preview revision. Sınır: operatör görevi/mesafesi ve profile resolution değişirse yeniden değerlendir. |
| Upper limit/offset adres sanılabilir. | Sayısal native alanların anlamı kanıtsız eşlenmiş. | Vendor schema bazı alanları farklı temsil edebilir; string isim tek başına yeterli olmaz. | Structured address kimliğini source schema kanıtıyla ayır; limit minimum/maximum metadata'sıdır. | Test: farklı address ama aynı upper limit eşit kabul edilmez; bütün address alanları eşleşir. Rollback: önceki immutable binding contract. Sınır: yeni driver/schema feature qualification gerekir. |
| Komut biti fiziksel feedback gibi gösterilebilir. | Operatör eylemiyle makine gerçeği tek state'e birleştirilmiş. | Feedback olmayan neutral demo request state gösterebilir; fiziksel çalışma diye etiketleyemez. | Request ve feedback role ayrı; quality/stale/comm-loss UNKNOWN. | Test: command true + absent/stale feedback → fiziksel running gösterilmez. Rollback: son approved design/binding contract. Sınır: gerçek feedback/saha doğrulaması insan kabulüdür. |

Sonuç yalnız bu sınırlı contract/test adaylarını tanımlar. Daha kısa çıktı veya offline PASS native qualification ve vendor/panel kanıtı yerine geçmez.
