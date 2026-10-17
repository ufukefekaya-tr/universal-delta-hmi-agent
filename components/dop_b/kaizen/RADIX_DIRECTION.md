# Adres tabanı ile erişim yetkisini ayrı tutmak

Gözlem: DVP X/Y native adres metni sekizlik, M/S/D onluktur. Aynı Y10 string'ini onluk10 kabul etmek başka fiziksel noktaya götürür. Driver tablosundaki bit/word selector read/write yetkisi değildir.

Kök neden: Tek decimal regex ve index parser bütün alanlara uygulanmıştı. Erişim hakkı yalnız tag kataloğunda bulunuyordu; yanlış katalog girdisi physical input write'ını kabul ettirebilirdi.

Karşı görüş: V1 bölgelerine X/Y eklemek daha küçük değişikliktir. Bu eski sözleşmenin anlamını sessiz değiştirir, Y8/Y9 alias'larını ve fake X ReadWrite metadata'sını taşır. Device code128/129'u native MemType sanmak da ayrı bir alanı bozar.

Minimum değişiklik: V1 byte/semantik davranışı korunur. Ayrı registered v2 her bölgeye radix ve normal-operation access bağlar; canonical rakamlar parsing öncesi sınanır. Native source/candidate ve her bind yönü, service onaylı IR ve helper authority aynı sözleşmeyi kullanır. Project tag izni ayrıca daha dar olabilir.

Test:256 X read/X-write-refusal ve256 Y read/write noktası,7→10/77→100/377→overflow, forgedReadWrite X, source/header/source-driver pin, metadata/radix/region drift, yeni ve eski authority freshness, dokuz gerçek MCP aracı ve actual B10 readonly indicator candidate. Var olan v1 M1/M10 anlamı ve old source byte'ları korunur.

Rollback: Mevcut kaynak ve authority dosyaları değişmez; v2 contract/candidate ayrı output-dir'dedir. Yeni profile/source SHA eski onayı geçersiz kılar. Driver typo veya runtime/physical sorununda önceki committed v1/profil korunur.

Genellenebilirlik sınırı: Base8 endpoint ve normal X/Y erişimi bu exact Delta DVP sürücüsünün kanıtıdır. Başka marka/protokol/word length/sign/byte order veya force/debug davranışı buradan türetilmez. DLL bit/word mode'undan permission çıkarılmaz; native pixels/PLC/panel kabulü ayrı kalır.
