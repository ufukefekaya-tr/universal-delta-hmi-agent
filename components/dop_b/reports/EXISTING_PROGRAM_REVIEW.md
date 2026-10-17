# Bağımsız inceleme — mevcut programda inert yazı kaldırma

Kabul **PASS**, yalnız source-pinned inert literal silme için. Uygulayıcıdan ayrı, salt okunur denetmen 647/647 unique testi 176.225 saniyede çalıştırdı: failure/error/skip sıfır. 71 source hash ve test-ID sırası root ile eşit; önce/sonra değişmedi. Revision `9121d6a0bb7b8a72ee9a2f140b60d283ea97bccf819b1cfc304c5168ffdc606b`. Yeni testler 14 native, 9 service ve 1 gerçek SDK akışıdır.

115 descriptor karşı örneğinde 111 typed ret ve 4 meşru kabul; ayrıca 10 native graph negative probe incelendi. E1 kaybolan/okunamayan dependency hatası dört bağımsız örnekle kapandı. Beklenen gövde emitter'dan ayrıldı: IR ve immutable kaynak aralıklarından bağımsız çıkarma kullanıyor. Önceki framing, duplicate/missing record, ASCII ve stale descriptor kusurları da açık ret veriyor. Dar kapsamda önemli açık yok; denetmen paylaşılan dosya değiştirmedi.

Gerçek ayrı SDK sunucusuyla üretilip kaydedilen **tarafsız, özgün byte fixture** 3 sayfa, 8 silme ve 5 survivor içerir. Aday SHA `21b0c5d45e38eae0f98a091b7c6e8d6947129036dd378afdbb10c141973dd7c2`; 1.918 dosya byte, 9.178 gövde byte. Denetmen geçici fixture temizlenmeden dosyayı yeniden açtı; bağımsız aralık çıkarma/geri koyma, survivor byte'ları, tail/thumbnail/prefix37, declared length, fresh-session replay ve değişmeyen kaynak kontrolleri geçti. Bu fixture üretici tarafından oluşturulmuş referans değildir.

Gerçek C3BA kaynakta 166 silme / 122 survivor ayrıca bağımsız olarak **bellekte** doğrulandı. Private source için kaydedilmiş SDK adayı üretilmedi; dış kaynak/proje yazımı sıfır. Bu iki kanıt birbirinin yerine sunulmaz.

Bu kabul görünüm/font/geometri, PNG arka plan, signed fractional keypad, quality/interlock, diğer model/aile, native pixel, vendor compile, runtime veya panel kabulü vermez. Bütün V1 ve toplu presentation paketi açık. [Exact milestone](EXISTING_PROGRAM_MILESTONE.json), [root testler](python_tests.json), [native kanıt](EXISTING_PROGRAM_NATIVE_FOCUS.json).
