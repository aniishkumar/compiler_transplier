const fs = require('fs');
let _inputBuf = '';
function prompt() {
    while (true) {
        let _start = 0;
        while (_start < _inputBuf.length && _inputBuf.charCodeAt(_start) <= 32) {
            _start = _start + 1;
        }
        if (_start < _inputBuf.length) {
            let _end = _start;
            while (_end < _inputBuf.length && _inputBuf.charCodeAt(_end) > 32) {
                _end = _end + 1;
            }
            let token = _inputBuf.slice(_start, _end);
            _inputBuf = _inputBuf.slice(_end);
            return token;
        }
        let buf = Buffer.alloc(1024);
        let n = fs.readSync(0, buf, 0, 1024);
        if (n == 0) {
            return '';
        }
        _inputBuf = _inputBuf + buf.toString('utf-8', 0, n);
    }
    return '';
}
class Employee {
    constructor(id = 0, name = "", salary = 0.0) {
        this.id = id;
        this.name = name;
        this.salary = salary;
    }
}

function display(ptr, n) {
    for (let i = 0; (i < n.value); i++) {
        console.log("\nEmployee %d", (i + 1));
        console.log("ID: %d", ptr[i].id);
        console.log("Name: %s", ptr[i].name);
        console.log("Salary: %s", Number(ptr[i].salary).toFixed(2));
    }
}
function main() {
    let n = { value: 0 };
    process.stdout.write(require("util").format("Enter number of employees: "));
    n.value = parseInt(prompt() || '0', 10);
    let ptr = null;
    ptr = Array.from({ length: n.value }, () => new Employee());
    if ((ptr == null)) {
        console.log("Memory allocation failed!");
        return 1;
    }
    for (let i = 0; (i < n.value); i++) {
        console.log("\nEnter Employee %d details", (i + 1));
        process.stdout.write(require("util").format("Enter ID: "));
        ptr[i].id = parseInt(prompt() || '0', 10);
        process.stdout.write(require("util").format("Enter Name: "));
        ptr[i].name = prompt() || '';
        process.stdout.write(require("util").format("Enter Salary: "));
        ptr[i].salary = parseFloat(prompt() || '0');
    }
    console.log("\n----- Employee Records -----");
    display(ptr, n);
    ptr = null;
    console.log("\nMemory successfully freed!");
    return 0;
}
process.exitCode = main();
