"""Domain availability via registry RDAP (404 = not registered). Prints a table."""
import requests, time
from concurrent.futures import ThreadPoolExecutor
N0 = """FinRehearse CloseReady PostReady ReadyToPost TcodeReady TcodeDojo ErpDojo FinDojo FinanceDojo TheCloseRoom
MockClose MockPosting PostingLab FinSimLab FinSimulate SimulateFinance ErpPracticeLab ErpRehearsal ErpReady GoLivePrep
CutoverReady CutoverPrep UatReady SandboxFinance FinSandbox TestClientLab Client800 DeskReadyFinance DayOneFinance FirstDayFinance
OfferReadyFinance HireReadyFinance FinInterviewPrep FinPrepHub PrepToPost PostAndPass PassTheClose CrackTheClose CloseTheInterview BalancedHire
DrCrReady DrCrLab TrialBalanceLab ReconReady ReconLab ZeroDifference ZeroVarianceLab MonthEndReady MonthEndLab MonthEndDojo
PeriodCloseLab CloseCycleLab R2RReady P2PReady O2CReady ProcureToHired RecordToRole OrderToOffer ThreeWayMatchLab GRIRReady
OpenItemLab JournalReady JournalDrill PostingDrill FinanceDrill AccountsGym FinanceGym TcodeGym ErpGym BooksGym
BooksReady BookToJob BooksToJobs SkillToSeat DeskTrained ErpTrained HandsOnFinance HandsOnErp FinHandsOn RealEntryLab
LiveEntryLab ShadowCloseLab InterviewDesk FinRoleReady RoleReadyLab ClosePractice PostingPractice FinTrialRun DryRunFinance FinMockDesk
CloseDeskLab GoLiveDesk EntryToOffer CreditToCareer DebitToDesk FirstPostingLab NextPosting HiredEntry OfferPosted TickAndTie""".split()
N = """FinRehearse TcodeReady TcodeDojo ErpDojo MockClose MockPosting SimulateFinance ErpPracticeLab ErpRehearsal GoLivePrep CutoverReady CutoverPrep TestClientLab Client800 DeskReadyFinance FirstDayFinance HireReadyFinance FinInterviewPrep FinPrepHub PostAndPass PassTheClose CrackTheClose CloseTheInterview BalancedHire DrCrReady TrialBalanceLab ZeroVarianceLab MonthEndLab MonthEndDojo PeriodCloseLab CloseCycleLab R2RReady P2PReady O2CReady ProcureToHired RecordToRole OrderToOffer ThreeWayMatchLab GRIRReady OpenItemLab PostingDrill AccountsGym TcodeGym BooksGym BookToJob BooksToJobs SkillToSeat DeskTrained ErpTrained FinHandsOn RealEntryLab LiveEntryLab ShadowCloseLab FinRoleReady PostingPractice FinTrialRun FinMockDesk CloseDeskLab EntryToOffer CreditToCareer DebitToDesk FirstPostingLab HiredEntry OfferPosted""".split()
boot = requests.get("https://data.iana.org/rdap/dns.json", timeout=20).json()
IN = [u for svc in boot["services"] if "in" in svc[0] for u in svc[1]]
print("IN RDAP", IN)
INB = IN[0].rstrip("/")
def rd(url):
    for _ in range(3):
        try:
            r = requests.get(url, timeout=20, headers={"Accept": "application/rdap+json"})
            if r.status_code == 404: return "FREE"
            if r.status_code == 200: return "taken"
            if r.status_code == 429: time.sleep(3); continue
            return f"?{r.status_code}"
        except Exception as e:
            time.sleep(2)
    return "?err"
def one(n):
    d = n.lower()
    return n, rd(f"https://rdap.verisign.com/com/v1/domain/{d}.com"), rd(f"{INB}/domain/{d}.in")
with ThreadPoolExecutor(6) as ex:
    for n, c, i in ex.map(one, N):
        print(f"DOM|{n}|{c}|{i}")
print("COUNT", len(N))
