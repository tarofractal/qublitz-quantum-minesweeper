OPENQASM 3.0;
include "stdgates.inc";
bit[2] syn;
bit[3] verify;
qubit[3] d;
qubit[2] a;
h d[0];
barrier d[0], d[1], d[2], a[0], a[1];
cx d[0], d[1];
cx d[0], d[2];
barrier d[0], d[1], d[2], a[0], a[1];
y d[1];
barrier d[0], d[1], d[2], a[0], a[1];
cx d[0], a[0];
cx d[1], a[0];
cx d[1], a[1];
cx d[2], a[1];
barrier d[0], d[1], d[2], a[0], a[1];
syn[0] = measure a[0];
syn[1] = measure a[1];
if (syn == 1) {
  y d[0];
}
if (syn == 3) {
  y d[1];
}
if (syn == 2) {
  y d[2];
}
barrier d[0], d[1], d[2], a[0], a[1];
cx d[0], d[2];
cx d[0], d[1];
barrier d[0], d[1], d[2], a[0], a[1];
h d[0];
verify[0] = measure d[0];
verify[1] = measure d[1];
verify[2] = measure d[2];
