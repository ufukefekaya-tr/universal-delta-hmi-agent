# Bağımsız teknik inceleme — üç kaynakla çok sayfa

**Bounded offline PASS.** Root ve ayrı salt-okunur denetmen590/590 unique testi0failure/error/skip ile çalıştırdı. Root126.892s, independent127.533s;62 source hash ve tam test ID listesi exact eşittir. Revision `1488881f01d6c61db8b1e861058dd44063b31e08ce8d6fbafcd5d33708c12075`. İnceleme HEADdb0f4c üzerinde yeni frozen kaynak byte'larıyla yapıldı; HEAD'in eski test revision'ı kabul edilmedi.

## Bulgu M1 — typed olmayan işlem ayracı

Tetikleyici: geçerli graph/aux işleminde op, kind veya forwarded set_property.key alanını list/object yapmak. Kanıt: ilk frozen module'de altı örnek membership işlemlerinde ham TypeError üretti; JSON structural bound bunu engellemiyordu. Etki: malformed public explicit-operation yolu tanımlı HmiError sözleşmesinden çıkabiliyordu.

Düzeltme: her ayracın string tipini membership veya eski control property handler'ına göndermeden doğrulama; genel exception yakalama eklenmedi. Tekrar test: altı karşı örnek typed PROGRAM_SCOPE/INVALID_AUX_OPERATION/INVALID_OPERATION oldu; sonraki no-op byte exact ve kaynaklar değişmez kaldı. **CLOSED**. Module SHAca12ef1c4aff2a28c6ea51c48cea19c32b02d5a7513dddf718a8560adfc186d3; multipage tests2683290af1eea397953ff2d0890dea473b008746c2c68ebafc2eb87ef1b1c7e1.

## Ayrı karşı kontroller

- 248 descriptor substitution:247 typed refusal + unchanged qualified=True accepted.
- 316 unmanaged page/aux record mutation: tamamı typed rejected.
- 75 rehashed public-profile case:74 typed refusal + original qualification accepted; rejected session sızmadı.
- 19 source/profile/witness/authority dependency × missing/changed:38 typed refusal.
- 12 actual saved-candidate mutation: yapısal geçerli M4→M5, alternate valid goto/name pair, owner drop/add ve page order dâhil tamamı onaylı niyette reddedildi.

Native verifier'ın başka yapısal geçerli düzenleri kabul edebilmesi beklenen davranıştır. Onaylı niyetin **bütün** gövdeyle karşılaştırılması service _candidate_matches içinde ayrıca zorunludur; shape PASS tek başına tasarım kabulü değildir.

## Gerçek dosya

Actual9SDK **55,577-byte** candidate SHA52852387fdbc9b03b8d0f2565e7377b3c2fafd6c62096499e76867a06f85ab99,3pages/13owners. IR/receipt operations yeniden derlenmiş listeyle eşit; replay bütün file byte'larında exact. Denetmen service/native operation emitter kullanmadan donor kayıtları + IR'den ayrı body kurdu: **52,087-byte**, SHAd707acdbbadd522792d75f17f81b0468e1a58a97fd75dd79c810d07f3366e59f exact.

Original globals/HMIPortNr0=2, ilk page header/action, BMP ve prefix37 korunur. Yeni page'lerde Action0 bulunur. Generated owners/pages çıkarılıp owned empty Tag başlangıcı tersine alınca bütün original body geri gelir. Actual c16e6 target/c7830 controls/c73e18 auxiliary SHA'ları değişmedi. Bu candidate UINT rawF0 kullanır; önceki savedF2 proof ayrı kalır. [Probe](MULTIPAGE_GENUINE_PROBE.json).

Açık önemli bulgu0 bu bounded stored-file kapsamı içindir. Native piksel yakalama kapsamı uygun değildi ve reddedildi; UI window metadata'sı piksel PASS sayılmadı. Vendor açma/derleme/simülasyon, navigation/touch/PLC/communication-loss runtime, fiziksel kabul ve tam V1 açık kalır. [Milestone](MULTIPAGE_MILESTONE.json), [sözleşme](../docs/MULTIPAGE_PROGRAM.md).
