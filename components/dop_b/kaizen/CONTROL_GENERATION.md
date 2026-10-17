# Vendor kaydı ile kontrol üretimi

Gözlem: description'da yazan türü temel almak yanlış buton üretir; generic donor'un yalnız SubType'ını değiştirmek native macro/voice/companion farklarını kaybettirir. Ayrı vendor Set/Reset/Push/Kalıcı ve numeric input/display owner'ları, özellik görüntüsüyle eşleştiğinde saklanan yapılandırma kanıtı elde edilir. Runtime basma/bırakma hâlâ ayrı testtir.

Kök neden: kaynak nesne türü, görünür başlık, PLC komut isteği ve gerçek feedback aynı kabul edilmiştir. Minimum düzeltme altı exact donor'u ayrı pinlemek, tür dönüşümünü reddetmek ve tek kaynak namespace'inde bütün-gövde beklenen değer doğrulamasıdır. Retained referans owner'lar temiz yeni program yerine geçmez.

Karşı bulgu: kaynak korunurken 41-byte decoded prefix'in son DWORD'u eski gövde uzunluğunda kaldı. Gerçek blank→saved farkı ve farklı gerçek kaynaklar bu alanı doğruladı. İlk 37 byte korunur, bilinen declaration mutasyonda yeniden hesaplanır. Önceki boyut değiştiren dosya deneylerinin bütünlük hükmü bu eksik kontrol açısından geri çekilir; no-op byte koruma ve salt-okunur kanıtları bundan etkilenmez.

Karşı denetim K4: doğru yeniden hash'lenmiş fakat null/list nested control contract'leri servis katmanında ham exception üretti. Native shape doğrulaması donor dereference önüne alındı. Public beş-case regresyonu ve bağımsız altı-case/192-probe incelemesi kapanışı sınadı. Builder görüntü okuması 10 MiB+1 ile sınırlandı.

Rollback: kaynak değişmez; ayrı aday ve ayrı calibration revision'ı atılır, önceki committed yazıcı kullanılabilir. Genel ders native alanı veya driver'ı bütün aileye yaymak değildir. Gerçek vendor/panel kabulü exact dosya/model/sürücüye bağlı kalır. [İnceleme](../reports/CONTROL_GENERATION_REVIEW.md).
