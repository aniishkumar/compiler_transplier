function square(n) {
    return n * n;
}

let numbers = [2, 4, 6, 8, 10];
let sum = 0;
for (let i = 0; i < 5; i++) {
    sum += square(numbers[i]);
}
console.log(sum);
