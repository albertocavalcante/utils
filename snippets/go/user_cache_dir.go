package main

import (
	"fmt"
	"os"
)

func main() {
	userCacheDir, err := os.UserCacheDir()
	if err != nil {
		panic(err)
	}

	fmt.Printf("User cache dir: %s\n", userCacheDir)
}
