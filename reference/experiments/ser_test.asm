; =================================================================
; QL Serial Block String Test (SER2H)
; =================================================================

START
            ; 1. Open channel "SER2H"
            lea     SERNAME,a0          
            moveq   #1,d0               ; IO.OPEN ($01)
            trap    #2                  
            tst.l   d0                  
            bne.s   EXIT                
            
            move.l  a0,d7               ; Save Channel ID pointer in D7

            ; 2. Prepare message pointer and loop counter
            lea     MSG,a1              
            move.w  (a1)+,d6            ; Get string length into D6

SEND_LOOP
            move.b  (a1)+,d1            ; Get next byte into D1

            move.l  d7,a3               ; Channel ID pointer into A3
            moveq   #5,d0               ; Operation code $05 (iob.sbyt)
            trap    #3                  ; Send single byte

            subq.w  #1,d6               ; Decrement character counter
            bne.s   SEND_LOOP           ; Repeat until all bytes sent

            ; 3. Close the channel
            move.l  d7,a0               
            moveq   #2,d0               ; IO.CLOSE ($02)
            trap    #2                  

EXIT
            rts                         

SERNAME
            dc.w    5                   
            dc.b    'SER2H'

MSG
            dc.w    15                  
            dc.b    'Hello from QL!',10  

            END