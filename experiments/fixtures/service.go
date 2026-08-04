// 주문 서비스 — 픽스처 (Go 프로젝트 유형)
package service

import "time"

// User 는 계정을 나타낸다.
type User struct {
	ID    int64
	Email string
}

type Order struct {
	ID     int64
	UserID int64
	Total  int
	Placed time.Time
}

// 함정: 인터페이스는 struct 가 아님 (정답 제외)
type Repository interface {
	Save(o Order) error
}

type LineItem struct {
	SKU string
	Qty int
}

// 함정: 타입 별칭은 struct 가 아님 (정답 제외)
type OrderID = int64

type Invoice struct {
	Order   Order
	Issued  time.Time
	PaidAt  *time.Time
}

func NewOrder(u User, items []LineItem) Order {
	total := 0
	for _, it := range items {
		total += it.Qty
	}
	return Order{UserID: u.ID, Total: total}
}
