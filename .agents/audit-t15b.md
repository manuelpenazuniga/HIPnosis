Auditoría adversarial de core/parity.py (comparador rtol/atol, F-09). NO ejecutes nada: razoná.
Es el que decide PASS/FAIL del port → un bug da certificado con cifras falsas (F-17). Inputs CONCRETOS:
1. compare_floats fórmula close = abs(a-e) <= atol + rtol*abs(e): ¿correcta? ¿expected=0 (solo atol)? ¿a=-e? ¿signo?
2. nan/inf: [nan]vs[nan]→ok?; [inf]vs[inf]→ok, [inf]vs[-inf]→False; ¿nan colándose como PASS falso?
3. extract_floats: regex captura mal (números en paths '3.0', rangos '1-2', '.5', '5.', '1.2e-5')? ¿conteo espurio?
4. conteo distinto: ¿siempre antes de comparar (sin IndexError)?
5. check_self_check: ¿un 'FAIL: PASS not reached' daría PASS falso por contener 'PASS'?
6. listas [] vs [] → ¿ok o error? ¿correcto para 'nada que comparar'?
Leé core/parity.py y tests/test_parity.py en /Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t15b/orchestrator/.
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`. Por hallazgo: severidad + parity.py:línea + input + fix. ÚLTIMA línea `END_AUDIT`.
