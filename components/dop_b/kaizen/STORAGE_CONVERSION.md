# Kaynak türü ile dönüşüm yetkisini ayır

Gözlem: gerçek neutral library UINT16 içeriyordu; static primary reader/writer/compiler INT16 biçimini doğruladı. Kaynağın property kanıtını signed olarak değiştirmek yanlış olurdu.

Kök neden: immutable donor storage ile explicit new-clone storage transformation aynı yetki değildi. Karşı görüş: signed donor yoksa companion alanları tahmin edilir. Native reader/setter tek+0x59 byte'ını yazar; writer ve addressview+0x38/+0x21 doğrudan formatı taşır; signedrange/keypad/renderer bu formatı kullanır. Sourceguard bütün disabled feature/offset/macroları ve raw ownerları ayrıca sınırlar. Bu static kanıt runtime kabulü değildir.

Minimum değişiklik: ayrı hash/model/version/authority descriptor ve explicit fresh-owner conversion; MemLen1 aynı, MemFmt2→1; sıradan numeric edit immutable storage kalır. Eski source/donor/property UINT, diğer genişlik/F>0/scaling kapalı.

S1 tetikleyici: root expected-body path generic numeric checker eşit limitleri kabul etti. Etki: plan erken kabulü native signed guard ile tutarsızdı. Pure verify_converted eklenince−32768..−32768 ve canonical olmayan limitler preflight'ta reddedildi;623root/independent ve424negative probe geçti.

Rollback: eski source-qualified UINT profile ve604/49b1ae16 source commit kullanılabilir; kaynak dosyalar değişmedi. Genel sınır: yalnız exactB10/4.00.07.04 typed source/proof; DOP100/signed donor/vendor/panel garantisi yok.
